import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export default function Modal({ title, id, onClose, className = "", children }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = dialogRef.current;
    (dialog.querySelector("input:checked:not([disabled])") || dialog.querySelector("input:not([disabled]), select:not([disabled])") || dialog.querySelector("button:not([disabled])"))?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (document.fullscreenElement) { void document.exitFullscreen().catch(() => {}); return; }
        closeRef.current();
      }
      if (event.key !== "Tab") return;
      const scope = document.fullscreenElement && dialog.contains(document.fullscreenElement) ? document.fullscreenElement : dialog;
      const controls = [...scope.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]')];
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    dialog.addEventListener("keydown", onKey);
    return () => { dialog.removeEventListener("keydown", onKey); previous?.focus(); };
  }, []);
  return createPortal(
    <div className="app-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={`app-modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={id} ref={dialogRef}>
        <header><h2 id={id}>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={22} /></button></header>
        {children}
      </section>
    </div>, document.body
  );
}
