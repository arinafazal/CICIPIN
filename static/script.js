document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.popup.show').forEach(function(popup) {
        setTimeout(function() {
            popup.classList.remove('show');
        }, 3000);
    });
});