document.addEventListener('DOMContentLoaded', () => {
    const countdownEl = document.getElementById('countdown');
    const submitBtn   = document.getElementById('submit-btn');

    if (!countdownEl || !submitBtn) return;

    const minutes = parseInt(countdownEl.dataset.expiryMinutes, 10) || 5;
    let seconds = minutes * 60;
    const timerEl = countdownEl.closest('.otp-timer');
    const otpInput = document.getElementById('otp');
    const form = otpInput?.form;
    let submitting = false;

    if (form) {
        const cleanInput = () => {
            const position = otpInput.selectionStart;
            const value = otpInput.value;
            otpInput.value = value.replace(/[^0-9]/g, '').slice(0, 6);
            if (position !== null) {
                const nextPosition = value.slice(0, position).replace(/[^0-9]/g, '').length;
                otpInput.setSelectionRange(nextPosition, nextPosition);
            }
            if (/^[0-9]{6}$/.test(otpInput.value) && seconds > 0 && !submitting) {
                form.requestSubmit(submitBtn);
            }
        };

        otpInput.addEventListener('beforeinput', (event) => {
            if (event.data && /[^0-9]/.test(event.data)) event.preventDefault();
        });
        otpInput.addEventListener('input', cleanInput);
        otpInput.addEventListener('change', cleanInput);
        otpInput.addEventListener('paste', (event) => {
            event.preventDefault();
            const digits = event.clipboardData.getData('text').replace(/[^0-9]/g, '');
            const start = otpInput.selectionStart;
            const end = otpInput.selectionEnd;
            const available = 6 - (otpInput.value.length - (end - start));
            otpInput.setRangeText(digits.slice(0, available), start, end, 'end');
            cleanInput();
        });
        form.addEventListener('submit', (event) => {
            if (submitting || seconds <= 0 || !/^[0-9]{6}$/.test(otpInput.value)) {
                event.preventDefault();
                return;
            }
            submitting = true;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Verifying...';
        });
        // Restore the button when returning through the browser's back cache.
        window.addEventListener('pageshow', () => {
            submitting = false;
            if (seconds > 0) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Verify OTP';
            }
        });
    }

    const tick = setInterval(() => {
        seconds--;
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        countdownEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;

        if (seconds <= 0) {
            clearInterval(tick);
            countdownEl.textContent = 'Expired';
            timerEl.classList.add('expired');
            
            // Disable button and update UI
            submitBtn.disabled = true;
            submitBtn.textContent = 'OTP Expired';
            submitBtn.style.opacity = '0.5';
            submitBtn.style.cursor = 'not-allowed';
        }
    }, 1000);
});
