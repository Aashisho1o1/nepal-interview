// Paid-version waiting list: a button to the Google Form set in WAITLIST_URL.

import { WAITLIST_URL } from "@/lib/copy";

export default function Waitlist() {
  return (
    <div className="card signin">
      <h2>Join the waiting list</h2>
      <p className="small">We&apos;ll let you know when the paid version opens, with more practice time and more countries.</p>
      {WAITLIST_URL ? (
        <a className="btn btn-secondary btn-block" href={WAITLIST_URL} target="_blank" rel="noopener noreferrer">Join the waiting list</a>
      ) : (
        <button type="button" className="btn btn-secondary btn-block" disabled>Opening soon</button>
      )}
    </div>
  );
}
