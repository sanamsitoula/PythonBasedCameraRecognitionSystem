"""
face_enrollment.py – Employee enrollment module for CCTV Phase 3.

Manages the full lifecycle of an employee's face data:
  add → update → re-enroll → deactivate → delete

Dependencies injected at construction time:
  face_engine : FaceRecognitionEngine  (face_recognition_engine.py)
  db_p3       : DatabaseManagerP3      (db_manager_p3.py)
"""

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

import cv2
import numpy as np

log = logging.getLogger("enrollment")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class EnrollmentResult:
    success:         bool
    employee_id:     str
    message:         str
    embedding_count: int = 0


# ---------------------------------------------------------------------------
# Enrollment engine
# ---------------------------------------------------------------------------
class FaceEnrollment:
    MIN_IMAGES         = 5
    RECOMMENDED_IMAGES = 20
    ENROLLMENT_DIR     = "enrollment"

    def __init__(
        self,
        face_engine,
        db_p3,
        enrollment_dir: str = "enrollment",
    ) -> None:
        """
        Parameters
        ----------
        face_engine : FaceRecognitionEngine
        db_p3       : DatabaseManagerP3
        enrollment_dir : str
            Root directory where per-employee image folders are stored.
        """
        self._engine        = face_engine
        self._db            = db_p3
        self._enrollment_dir = enrollment_dir
        os.makedirs(enrollment_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # Core operations
    # -----------------------------------------------------------------------
    def add_employee(
        self,
        employee_id: str,
        name: str,
        department: str,
        designation: str,
        image_paths: List[str],
    ) -> EnrollmentResult:
        """
        Enroll a new employee from a list of image file paths.

        Steps:
        1. Upsert employee record in DB.
        2. For each image: detect face, extract embedding, save to DB.
        3. Copy source images to enrollment/<employee_id>/.
        4. Require at least MIN_IMAGES successful embeddings to succeed.
        """
        if not image_paths:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message="No image paths provided.",
            )

        # 1. Create / update employee master record
        ok = self._db.ensure_employee(employee_id, name, department, designation)
        if not ok:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message="Failed to create employee record in database.",
            )

        # 2. Process images
        emp_dir = os.path.join(self._enrollment_dir, employee_id)
        os.makedirs(emp_dir, exist_ok=True)

        success_count  = 0
        skipped_count  = 0
        for idx, img_path in enumerate(image_paths):
            embedding = self._process_image(img_path, employee_id)
            if embedding is None:
                skipped_count += 1
                log.warning("No face detected in %s — skipped.", img_path)
                continue

            # Save embedding to DB
            angle = "frontal"   # default angle tag; extend later if needed
            emb_id = self._db.save_face_embedding(employee_id, embedding, img_path, angle)
            if emb_id == -1:
                skipped_count += 1
                log.warning("Failed to save embedding for %s from %s.", employee_id, img_path)
                continue

            # 3. Copy image to enrollment directory
            try:
                ext = os.path.splitext(img_path)[1].lower() or ".jpg"
                dst = os.path.join(emp_dir, f"{idx:04d}{ext}")
                shutil.copy2(img_path, dst)
            except OSError as exc:
                log.warning("Could not copy %s to enrollment dir: %s", img_path, exc)

            success_count += 1

        # 4. Enforce minimum threshold
        if success_count < self.MIN_IMAGES:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=(
                    f"Only {success_count} valid face(s) extracted from "
                    f"{len(image_paths)} image(s). Minimum required: {self.MIN_IMAGES}. "
                    f"Skipped: {skipped_count}."
                ),
                embedding_count=success_count,
            )

        log.info(
            "Enrolled %s (%s): %d embeddings saved (%d skipped).",
            name, employee_id, success_count, skipped_count,
        )
        return EnrollmentResult(
            success=True,
            employee_id=employee_id,
            message=(
                f"Successfully enrolled {name} with {success_count} face embedding(s). "
                f"{skipped_count} image(s) skipped."
            ),
            embedding_count=success_count,
        )

    def update_employee(
        self,
        employee_id: str,
        name: str = None,
        department: str = None,
        designation: str = None,
    ) -> EnrollmentResult:
        """
        Update employee metadata only (name / department / designation).
        Face embeddings are not touched.
        """
        # Fetch current record to fill in unchanged fields
        status_info = self.get_enrollment_status(employee_id)
        if not status_info:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=f"Employee {employee_id} not found.",
            )

        new_name        = name        or status_info.get("name",        "")
        new_department  = department  or status_info.get("department",  "")
        new_designation = designation or status_info.get("designation", "")

        ok = self._db.ensure_employee(employee_id, new_name, new_department, new_designation)
        if not ok:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message="Failed to update employee record in database.",
            )

        log.info("Updated metadata for employee %s.", employee_id)
        return EnrollmentResult(
            success=True,
            employee_id=employee_id,
            message=f"Metadata updated for {employee_id}.",
        )

    def re_enroll_face(
        self,
        employee_id: str,
        image_paths: List[str],
    ) -> EnrollmentResult:
        """
        Delete all existing embeddings for employee_id and re-enroll from
        the supplied image list.
        """
        # Remove old embeddings from DB
        ok = self._db.delete_employee_embeddings(employee_id)
        if not ok:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message="Failed to delete existing embeddings from database.",
            )

        # Remove old images from disk (best-effort)
        emp_dir = os.path.join(self._enrollment_dir, employee_id)
        if os.path.isdir(emp_dir):
            try:
                shutil.rmtree(emp_dir)
            except OSError as exc:
                log.warning("Could not remove old enrollment dir %s: %s", emp_dir, exc)

        # Fetch current name/dept/designation from the status helper
        status_info = self.get_enrollment_status(employee_id)
        name        = status_info.get("name",        employee_id)
        department  = status_info.get("department",  "")
        designation = status_info.get("designation", "")

        return self.add_employee(employee_id, name, department, designation, image_paths)

    def deactivate_employee(self, employee_id: str) -> EnrollmentResult:
        """Set employee status to 'inactive' in the database."""
        ok = self._db.update_employee_status(employee_id, "inactive")
        if not ok:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=f"Failed to deactivate employee {employee_id}.",
            )
        log.info("Employee %s deactivated.", employee_id)
        return EnrollmentResult(
            success=True,
            employee_id=employee_id,
            message=f"Employee {employee_id} has been deactivated.",
        )

    def delete_employee(self, employee_id: str) -> EnrollmentResult:
        """
        Soft-delete: set status to 'deleted', remove embeddings from DB
        and delete the enrollment image directory from disk.
        """
        # Mark as deleted in DB
        ok = self._db.update_employee_status(employee_id, "deleted")
        if not ok:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=f"Failed to mark employee {employee_id} as deleted.",
            )

        # Delete embeddings from DB
        self._db.delete_employee_embeddings(employee_id)

        # Delete images from disk (best-effort)
        emp_dir = os.path.join(self._enrollment_dir, employee_id)
        if os.path.isdir(emp_dir):
            try:
                shutil.rmtree(emp_dir)
                log.info("Deleted enrollment directory: %s", emp_dir)
            except OSError as exc:
                log.warning("Could not remove enrollment dir %s: %s", emp_dir, exc)

        log.info("Employee %s deleted from system.", employee_id)
        return EnrollmentResult(
            success=True,
            employee_id=employee_id,
            message=f"Employee {employee_id} deleted and embeddings removed.",
        )

    def enroll_from_directory(
        self,
        employee_id: str,
        name: str,
        department: str,
        designation: str,
        image_dir: str,
    ) -> EnrollmentResult:
        """
        Collect all JPEG / PNG images inside *image_dir* and call add_employee.
        """
        if not os.path.isdir(image_dir):
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=f"Directory not found: {image_dir}",
            )

        image_paths = []
        for fname in sorted(os.listdir(image_dir)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                image_paths.append(os.path.join(image_dir, fname))

        if not image_paths:
            return EnrollmentResult(
                success=False,
                employee_id=employee_id,
                message=f"No jpg/jpeg/png images found in {image_dir}.",
            )

        log.info(
            "enroll_from_directory: found %d images for %s in %s.",
            len(image_paths), employee_id, image_dir,
        )
        return self.add_employee(employee_id, name, department, designation, image_paths)

    def get_enrollment_status(self, employee_id: str) -> dict:
        """
        Return a summary dict for the given employee.

        Keys: employee_id, name, department, designation, image_count,
              status, last_enrolled.
        Returns an empty dict if the employee is not found.
        """
        try:
            all_employees = self._db.get_all_active_employees()
            for emp in all_employees:
                if emp["employee_id"] == employee_id:
                    image_count   = 0
                    last_enrolled = None

                    # Try to read from employee_face_master via a direct DB query
                    try:
                        with self._db._get_conn() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "SELECT image_count, last_enrolled "
                                    "FROM employee_face_master WHERE employee_id = %s",
                                    (employee_id,),
                                )
                                row = cur.fetchone()
                                if row:
                                    image_count   = row[0]
                                    last_enrolled = row[1]
                    except Exception:
                        pass   # DB may not have the face-master table yet

                    return {
                        "employee_id":   emp["employee_id"],
                        "name":          emp["employee_name"],
                        "department":    emp["department"],
                        "designation":   emp.get("designation", ""),
                        "image_count":   image_count,
                        "status":        "active",
                        "last_enrolled": str(last_enrolled) if last_enrolled else "Never",
                    }

            # Not in active list — try fetching regardless of status
            try:
                with self._db._get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT employee_id, employee_name, department, designation, status "
                            "FROM employee_master WHERE employee_id = %s",
                            (employee_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            return {
                                "employee_id": row[0],
                                "name":        row[1],
                                "department":  row[2],
                                "designation": row[3],
                                "image_count": 0,
                                "status":      row[4],
                                "last_enrolled": "Unknown",
                            }
            except Exception:
                pass

            return {}
        except Exception as exc:
            log.error("get_enrollment_status(%s) failed: %s", employee_id, exc)
            return {}

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------
    def _process_image(self, image_path: str, employee_id: str) -> Optional[np.ndarray]:
        """
        Load image with cv2, run face_engine.embed_face on it.
        Returns a float32 embedding array, or None if no face was found.
        """
        if not os.path.isfile(image_path):
            log.warning("Image not found: %s", image_path)
            return None

        img = cv2.imread(image_path)
        if img is None:
            log.warning("cv2 could not read image: %s", image_path)
            return None

        # Use detect_and_embed for the most reliable pipeline
        detection = self._engine.detect_and_embed(img)
        if detection is None or detection.embedding is None:
            return None

        return detection.embedding.astype(np.float32)
