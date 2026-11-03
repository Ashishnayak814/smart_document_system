document.addEventListener('DOMContentLoaded', function () {
    const toggles = document.querySelectorAll('.toggle-password');

    toggles.forEach(function (button) {
        button.addEventListener('click', function () {
            const input = this.parentElement.querySelector('input');
            const icon = this.querySelector('i');

            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });

    const dropzone = document.getElementById('dropzone');
    if (dropzone) {
        ['dragover', 'drop'].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function (event) {
                event.preventDefault();
                dropzone.classList.add('drag-over');
            });
        });

        ['dragleave'].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function () {
                dropzone.classList.remove('drag-over');
            });
        });
    }
});
