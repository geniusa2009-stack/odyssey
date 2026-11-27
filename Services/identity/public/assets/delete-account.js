'use strict';

(function () {
  const form = document.getElementById('delete-form');
  const email = document.getElementById('email');
  const password = document.getElementById('password');
  const confirmation = document.getElementById('confirmation');
  const submit = document.getElementById('submit');
  const status = document.getElementById('status');

  function ready() {
    return email.value.includes('@') && password.value.length > 0 && confirmation.value.trim() === 'DELETE';
  }
  [email, password, confirmation].forEach((el) => el.addEventListener('input', () => {
    submit.disabled = !ready();
  }));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!ready()) return;
    submit.disabled = true;
    status.textContent = 'Deleting…';
    try {
      const res = await fetch('/api/v1/auth/delete-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.value.trim(), password: password.value, confirmation: 'DELETE' }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        form.reset();
        status.textContent = body.data && body.data.pending
          ? 'Your account is locked and its data is being deleted. This finishes automatically.'
          : 'Your ODYSSEY account and all of its data have been deleted.';
        return;
      }
      status.textContent = res.status === 429
        ? 'Too many attempts. Please wait a few minutes and try again.'
        : 'The e-mail or password is not correct.';
    } catch {
      status.textContent = 'Could not reach the server. Please try again.';
    }
    password.value = '';
    submit.disabled = !ready();
  });
})();
