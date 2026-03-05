window.onload = function() {
    var popup = document.getElementById('popupMessage');
    if (popup) {
        // Menampilkan pop-up dengan menambahkan kelas 'show'
        popup.classList.add('show');

        // Menghilangkan pop-up setelah 3 detik
        setTimeout(function() {
            popup.classList.remove('show');
        }, 3000); // Pop-up akan hilang setelah 3 detik
    }
};