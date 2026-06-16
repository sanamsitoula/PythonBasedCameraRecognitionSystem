import { useEffect, useRef } from 'react';
import wsService from '../services/websocket';

/**
 * useWebSocket — subscribe to WebSocket events with automatic cleanup.
 *
 * @param {Object} handlers  e.g. { onAlert: fn, onOccupancyUpdate: fn }
 * @param {Array}  deps      dependency array (re-subscribe when these change)
 */
export default function useWebSocket(handlers = {}, deps = []) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    // Ensure connection is active
    wsService.connect();

    const entries = Object.entries(handlersRef.current);
    // Wrap in stable refs so unsubscribe works
    const stableHandlers = entries.map(([event, fn]) => {
      const stable = (...args) => handlersRef.current[event]?.(...args);
      wsService.subscribe(event, stable);
      return [event, stable];
    });

    return () => {
      stableHandlers.forEach(([event, stable]) => {
        wsService.unsubscribe(event, stable);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
