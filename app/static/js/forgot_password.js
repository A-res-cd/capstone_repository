document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('resetPasswordForm');
    const pass = document.getElementById('new_password');
    const confirm = document.getElementById('confirm_password');

    if (form && pass && confirm) {
        form.addEventListener('submit', (e) => {
            if (pass.value !== confirm.value) {
                e.preventDefault();
                // Apply error styling
                confirm.style.borderColor = '#A32D2D';
                confirm.style.boxShadow = '0 0 0 3px rgba(163,45,45,0.15)';
                
                // Show native browser tooltip error
                confirm.setCustomValidity('Passwords do not match.');
                confirm.reportValidity();
            } else {
                confirm.setCustomValidity('');
            }
        });

        // Reset error styling when user starts typing again
        confirm.addEventListener('input', () => {
            confirm.style.borderColor = '';
            confirm.style.boxShadow = '';
            confirm.setCustomValidity('');
        });
    }
});