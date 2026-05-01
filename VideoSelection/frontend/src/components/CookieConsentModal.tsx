import { useState } from "react";
import { extractCookies } from "../api/client";
import "./CookieConsentModal.css";

type ModalState = "idle" | "loading" | "error";

interface Props {
  onAccepted: () => void;
  onDeclined: () => void;
}

export default function CookieConsentModal({ onAccepted, onDeclined }: Props) {
  const [state, setState] = useState<ModalState>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleAccept() {
    setState("loading");
    const result = await extractCookies();
    if (result.success) {
      onAccepted();
    } else {
      setErrorMsg(result.error ?? "Please close Chrome and try again.");
      setState("error");
    }
  }

  return (
    <div className="cookie-modal__overlay">
      <div className="cookie-modal__box">
        <h2>Cookie Access Required</h2>
        <p>
          This app needs access to your YouTube cookies to download videos.
          Your cookies are stored locally and never sent to any external server.
        </p>

        {state === "idle" && (
          <div className="cookie-modal__actions">
            <button
              className="cookie-modal__btn cookie-modal__btn--accept"
              onClick={handleAccept}
            >
              Accept All Cookies
            </button>
            <button
              className="cookie-modal__btn cookie-modal__btn--decline"
              onClick={onDeclined}
            >
              Decline
            </button>
          </div>
        )}

        {state === "loading" && (
          <div className="cookie-modal__loading">
            <div className="cookie-modal__spinner" />
            <p>Extracting cookies from Chrome...</p>
          </div>
        )}

        {state === "error" && (
          <div className="cookie-modal__error">
            <p>{errorMsg}</p>
            <button
              className="cookie-modal__btn cookie-modal__btn--accept"
              onClick={handleAccept}
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
