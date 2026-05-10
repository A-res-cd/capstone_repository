document.addEventListener('DOMContentLoaded', () => {
    let seconds = 5 * 60;
    const countdownEl = document.getElementById('countdown');
    const submitBtn   = document.getElementById('submit-btn');
    
    if (!countdownEl || !submitBtn) return;

    const timerEl = countdownEl.closest('.otp-timer');

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