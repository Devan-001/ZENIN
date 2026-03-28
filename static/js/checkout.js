document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('checkoutForm');
  if (!form) {
    return;
  }

  var methodRows = document.querySelectorAll('.method-row');
  var radios = document.querySelectorAll('input[name="payment_method"]');

  var cardFields = document.getElementById('cardFields');
  var upiFields = document.getElementById('upiFields');

  var placeOrderBtn = document.getElementById('placeOrderBtn');
  var processingOverlay = document.getElementById('processingOverlay');

  var upiVerifyBtn = document.getElementById('verifyUpiBtn');
  var upiStatus = document.getElementById('upiStatus');
  var upiInput = document.getElementById('upi_id');

  var cardName = document.getElementById('card_name');
  var cardNumber = document.getElementById('card_number');
  var cardExpiry = document.getElementById('card_expiry');
  var cardCvv = document.getElementById('card_cvv');

  function setCardRequired(isRequired) {
    cardName.required = isRequired;
    cardNumber.required = isRequired;
    cardExpiry.required = isRequired;
    cardCvv.required = isRequired;
  }

  function setUpiRequired(isRequired) {
    upiInput.required = isRequired;
  }

  function setActiveRow(selectedValue) {
    methodRows.forEach(function (row) {
      var radio = row.querySelector('input[type="radio"]');
      if (radio && radio.value === selectedValue) {
        row.classList.add('active');
      } else {
        row.classList.remove('active');
      }
    });
  }

  function togglePaymentFields(selectedValue) {
    if (selectedValue === 'card') {
      cardFields.classList.remove('hidden');
      upiFields.classList.add('hidden');
      setCardRequired(true);
      setUpiRequired(false);
      upiStatus.textContent = '';
    } else if (selectedValue === 'upi') {
      cardFields.classList.add('hidden');
      upiFields.classList.remove('hidden');
      setCardRequired(false);
      setUpiRequired(true);
    } else {
      cardFields.classList.add('hidden');
      upiFields.classList.add('hidden');
      setCardRequired(false);
      setUpiRequired(false);
      upiStatus.textContent = '';
    }

    setActiveRow(selectedValue);
  }

  radios.forEach(function (radio) {
    radio.addEventListener('change', function () {
      togglePaymentFields(this.value);
    });
  });

  methodRows.forEach(function (row) {
    row.addEventListener('click', function (event) {
      if (event.target.tagName.toLowerCase() !== 'input') {
        var radio = row.querySelector('input[type="radio"]');
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });

  upiVerifyBtn.addEventListener('click', function () {
    var value = upiInput.value.trim();
    if (!value) {
      upiStatus.textContent = 'Enter a UPI ID first.';
      upiStatus.style.color = '#b42318';
      return;
    }
    upiStatus.textContent = 'UPI ID verified successfully (dummy).';
    upiStatus.style.color = '#0f8a5f';
  });

  var selected = document.querySelector('input[name="payment_method"]:checked');
  togglePaymentFields(selected ? selected.value : 'card');

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    if (form.dataset.processing === 'true') {
      return;
    }
    form.dataset.processing = 'true';

    placeOrderBtn.style.display = 'none';
    processingOverlay.classList.add('show');
    processingOverlay.setAttribute('aria-hidden', 'false');

    setTimeout(function () {
      alert('Payment Successful!');
      e.target.submit();
    }, 2500);
  });
});
