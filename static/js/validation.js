/**
 * validation.js
 * Client-side validation utilities for Zenin registration & forms.
 */

/**
 * Evaluate password strength (0–4).
 * Returns { score, label, color }
 */
function evaluatePasswordStrength(password) {
  let score = 0;
  if (password.length >= 8)  score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  const levels = [
    { label: 'Too short',  color: '#e63946' },
    { label: 'Weak',       color: '#e63946' },
    { label: 'Fair',       color: '#d9a227' },
    { label: 'Good',       color: '#457b9d' },
    { label: 'Strong',     color: '#2d9c4f' },
    { label: 'Very Strong',color: '#2d9c4f' },
  ];
  return { score, ...levels[Math.min(score, levels.length - 1)] };
}

/**
 * Simple RFC 5322-ish email check.
 */
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
}

/**
 * Project-specific email rule:
 * - must be valid format
 * - local part must start with lowercase letter
 */
function isValidProjectEmail(email) {
  if (!isValidEmail(email)) return false;
  return /^[a-z][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}$/i.test(email) && /^[a-z]/.test(email);
}

function isValidPhoneNumber(phone) {
  return /^\d{10}$/.test(phone);
}

function attachPasswordToggle(inputEl) {
  if (!inputEl) return;
  if (inputEl.parentElement && inputEl.parentElement.classList.contains('password-input-wrap')) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'password-input-wrap';
  inputEl.parentNode.insertBefore(wrapper, inputEl);
  wrapper.appendChild(inputEl);

  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'password-toggle-btn';
  toggleBtn.textContent = 'Show';
  toggleBtn.setAttribute('aria-label', 'Toggle password visibility');

  toggleBtn.addEventListener('click', function () {
    const nextType = inputEl.type === 'password' ? 'text' : 'password';
    inputEl.type = nextType;
    toggleBtn.textContent = nextType === 'password' ? 'Show' : 'Hide';
  });

  wrapper.appendChild(toggleBtn);
}

/**
 * Initialise validation for any registration form.
 * Options: {passwordField, confirmField, emailField, phoneField, strengthBar, strengthLabel, strengthGroup}
 */
function initRegisterValidation(formId, opts) {
  const form = document.getElementById(formId);
  if (!form) return;

  const pwField      = document.getElementById(opts.passwordField);
  const confirmField = opts.confirmField ? document.getElementById(opts.confirmField) : null;
  const emailField   = opts.emailField   ? document.getElementById(opts.emailField)   : null;
  const phoneField   = opts.phoneField   ? document.getElementById(opts.phoneField)   : null;
  const barEl        = opts.strengthBar  ? document.getElementById(opts.strengthBar)  : null;
  const labelEl      = opts.strengthLabel? document.getElementById(opts.strengthLabel): null;
  const groupEl      = opts.strengthGroup? document.getElementById(opts.strengthGroup): null;

  attachPasswordToggle(pwField);
  attachPasswordToggle(confirmField);

  // Live password strength meter
  if (pwField && barEl && labelEl && groupEl) {
    pwField.addEventListener('input', function () {
      const val = this.value;
      if (val.length === 0) {
        groupEl.style.display = 'none';
        return;
      }
      groupEl.style.display = 'block';
      const result = evaluatePasswordStrength(val);
      const pct = Math.min((result.score / 5) * 100, 100);
      barEl.style.width  = pct + '%';
      barEl.style.background = result.color;
      labelEl.textContent = result.label;
      labelEl.style.color = result.color;
    });
  }

  // Form submission validation
  form.addEventListener('submit', function (e) {
    let valid = true;
    const errors = [];

    // Email format check
    const emailValue = emailField ? emailField.value.trim() : '';
    if (emailField && !isValidProjectEmail(emailValue)) {
      errors.push('Email must be valid and start with a lowercase letter.');
      emailField.style.borderColor = '#e63946';
      valid = false;
    } else if (emailField) {
      emailField.style.borderColor = '';
    }

    if (phoneField && !isValidPhoneNumber(phoneField.value.trim())) {
      errors.push('Phone number must be exactly 10 digits.');
      phoneField.style.borderColor = '#e63946';
      valid = false;
    } else if (phoneField) {
      phoneField.style.borderColor = '';
    }

    // Password minimum length
    if (pwField && pwField.value.length < 8) {
      errors.push('Password must be at least 8 characters.');
      pwField.style.borderColor = '#e63946';
      valid = false;
    } else if (pwField) {
      pwField.style.borderColor = '';
    }

    // Passwords match
    if (confirmField && pwField && confirmField.value !== pwField.value) {
      errors.push('Passwords do not match.');
      confirmField.style.borderColor = '#e63946';
      valid = false;
    } else if (confirmField) {
      confirmField.style.borderColor = '';
    }

    // Required fields check (all inputs & selects inside the form)
    form.querySelectorAll('input[required], select[required], textarea[required]').forEach(function (el) {
      if (!el.value.trim()) {
        el.style.borderColor = '#e63946';
        valid = false;
        if (!errors.includes('Please fill in all required fields.')) {
          errors.push('Please fill in all required fields.');
        }
      } else {
        el.style.borderColor = '';
      }
    });

    if (!valid) {
      e.preventDefault();
      // Show errors cleanly via existing .field-error elements or an alert
      if (errors.length) {
        alert(errors.join('\n'));
      }
    }
  });

  // Clear per-field red border on input
  form.querySelectorAll('input, select, textarea').forEach(function (el) {
    el.addEventListener('input', function () {
      if (this.value.trim()) this.style.borderColor = '';
    });
  });
}
