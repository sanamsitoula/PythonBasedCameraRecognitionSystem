import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { RiCloseLine } from 'react-icons/ri';

/**
 * Reusable Bootstrap-styled modal portal.
 *
 * Props:
 *   show, onHide, title, size ('sm'|'md'|'lg'|'xl'), children, footer,
 *   closeOnBackdrop (default true), scrollable
 */
export default function Modal({
  show,
  onHide,
  title,
  size = 'md',
  children,
  footer,
  closeOnBackdrop = true,
  scrollable = false,
}) {
  useEffect(() => {
    if (show) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [show]);

  if (!show) return null;

  const sizeClass = { sm: 'modal-sm', md: '', lg: 'modal-lg', xl: 'modal-xl' }[size] || '';

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className="modal-backdrop fade show"
        style={{ background: 'rgba(1,4,9,0.7)', zIndex: 1050 }}
        onClick={closeOnBackdrop ? onHide : undefined}
      />
      {/* Dialog */}
      <div
        className="modal fade show d-block"
        style={{ zIndex: 1055 }}
        onClick={closeOnBackdrop ? (e) => { if (e.target === e.currentTarget) onHide(); } : undefined}
      >
        <div className={`modal-dialog modal-dialog-centered ${sizeClass} ${scrollable ? 'modal-dialog-scrollable' : ''}`}>
          <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            {title !== undefined && (
              <div className="modal-header" style={{ borderBottom: '1px solid #30363d', padding: '14px 20px' }}>
                <h5 className="modal-title text-white fw-semibold" style={{ fontSize: 15 }}>{title}</h5>
                <button className="btn btn-link p-0 text-muted" onClick={onHide}>
                  <RiCloseLine size={20} />
                </button>
              </div>
            )}
            <div className="modal-body" style={{ padding: '20px' }}>
              {children}
            </div>
            {footer && (
              <div className="modal-footer" style={{ borderTop: '1px solid #30363d', padding: '12px 20px' }}>
                {footer}
              </div>
            )}
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
