import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
# used for image processing
from PIL import Image

# Memuat variabel dari file .env
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-cicipin-2024')  # Secret key untuk session

# Koneksi ke MongoDB menggunakan URI dan DB_NAME dari .env
# buat koneksi MongoDB dengan penanganan kesalahan agar aplikasi tidak langsung crash
# helper untuk memperkecil/memotong gambar agar ukurannya konsisten

def process_image(path, size=(600,400)):
    """Buka file di <path>, resize & center-crop menjadi `size` lalu timpa file.

    `size` adalah tuple (width, height). Gambar akan di-resize preserving
    aspect ratio lalu dipotong secara center-fit.
    """
    try:
        img = Image.open(path)
        img = img.convert('RGB')
        img.thumbnail((size[0], size[1]), Image.ANTIALIAS)
        # after thumbnail, image fits inside box but may not have exact size
        # create new image and paste center
        new_img = Image.new('RGB', size, (255,255,255))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        new_img.paste(img, (x, y))
        new_img.save(path)
    except Exception as e:
        # log but don't crash
        app.logger.warning("failed to process image %s: %s", path, e)

try:
    client = MongoClient(os.environ.get("MONGODB_URI"), serverSelectionTimeoutMS=5000)
    db = client[os.environ.get("DB_NAME")]
    # memaksa pemilihan server supaya koneksi diuji saat startup
    client.admin.command('ping')
    restaurants_collection = db["restaurants"]  # Mengakses collection restoran
except Exception as exc:
    # catat dan sediakan objek dummy supaya rute tidak mengakses None
    import logging
    logging.getLogger(__name__).error("Database connection failed: %s", exc)
    client = None
    db = None
    restaurants_collection = None

# Route untuk halaman login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Validasi login dengan username dan password
        if db is None:
            flash('Cannot log in: database unreachable', 'danger')
            return render_template('login.html')
        user = db.users.find_one({"username": username})

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])  # Menyimpan user_id di session
            session['username'] = username  # Menyimpan username di session
            flash('You have successfully logged in', 'success')
            return redirect(url_for('index'))  # Redirect ke halaman utama setelah login
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')  # Tampilkan halaman login jika GET request

# Route untuk halaman registrasi
@app.route('/register', methods=['GET', 'POST'])
def register():
    if "user_id" in session:  # Cek jika sudah login
        return redirect(url_for('index'))  # Jika sudah login, arahkan ke halaman utama

    if request.method == 'POST':
        if db is None:
            flash('Cannot register: database unreachable', 'danger')
            return redirect(url_for('register'))

        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        try:
            # Periksa jika pengguna sudah terdaftar
            existing_user = db.users.find_one({"username": username})
            if existing_user:
                flash("Username already exists", "danger")
                return redirect(url_for('register'))

            # Simpan data pengguna baru ke MongoDB
            db.users.insert_one({"username": username, "password": hashed_password})
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for('login'))
        except Exception as exc:
            app.logger.error("register error: %s", exc)
            flash('Failed to create account, please try again later.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')  # Tampilkan halaman registrasi

# Route untuk halaman utama (index)
@app.route('/')
def index():
    if "user_id" not in session:  # Cek jika pengguna belum login
        return redirect(url_for("login"))  # Arahkan ke halaman login jika belum login

    # jika database belum terhubung, tampilkan pesan kosong
    if db is None:
        flash('Database unavailable, restoran tidak dapat ditampilkan', 'danger')
        return render_template('index.html', restaurants=[], recommended_restaurants=[], username=session.get('username'))

    # Mengambil data pencarian dari query params
    search_term = request.args.get('category') or None  # gunakan 'category' sebagai search_term untuk backward compat

    # hanya konversi jika disediakan, biarkan None bila kosong
    min_rating = request.args.get('min_rating')
    max_price = request.args.get('max_price')
    min_rating = float(min_rating) if min_rating else None
    max_price = float(max_price) if max_price else None

    # Mendapatkan restoran yang direkomendasikan
    recommended_restaurants = get_recommended_restaurants(search_term, min_rating)

    # Menampilkan restoran yang sesuai dengan filter
    restaurants = search_restaurants(search_term, min_rating, max_price)

    return render_template('index.html', restaurants=restaurants, recommended_restaurants=recommended_restaurants, username=session["username"])

# Fungsi untuk mencari restoran dengan filter
def compute_average_rating(restaurant):
    reviews = restaurant.get('reviews', [])
    if reviews:
        try:
            avg = sum(r.get('rating', 0) for r in reviews) / len(reviews)
        except Exception:
            avg = 0
        # store rounded 1 decimal place
        restaurant['average_rating'] = round(avg, 1)
    else:
        restaurant['average_rating'] = None
    return restaurant


def search_restaurants(search_term=None, min_rating=None, max_price=None):
    query = {}

    if search_term:
        # cari di name, category, atau address dengan regex case-insensitive
        query['$or'] = [
            {'name': {'$regex': search_term, '$options': 'i'}},
            {'category': {'$regex': search_term, '$options': 'i'}},
            {'address': {'$regex': search_term, '$options': 'i'}}
        ]

    # rating filter now uses computed average_rating available after retrieval
    # we'll filter in Python for simplicity

    if max_price is not None:
        # sertakan restoran yang belum punya field price (agar daftar tidak kosong)
        existing_or = query.get('$or', [])
        query['$or'] = existing_or + [
            {'price': {'$lte': max_price}},
            {'price': {'$exists': False}}
        ]

    restaurants = db.restaurants.find(query)
    result = []
    for restaurant in restaurants:
        compute_average_rating(restaurant)
        # apply min_rating filtering if needed
        if min_rating is not None:
            if restaurant['average_rating'] is None or restaurant['average_rating'] < min_rating:
                continue
        result.append(restaurant)
    return result

# Fungsi untuk mendapatkan restoran yang direkomendasikan
def get_recommended_restaurants(search_term=None, min_rating=None):
    query = {}
    if search_term:
        # cari di name, category, atau address
        query['$or'] = [
            {'name': {'$regex': search_term, '$options': 'i'}},
            {'category': {'$regex': search_term, '$options': 'i'}},
            {'address': {'$regex': search_term, '$options': 'i'}}
        ]
    restaurants = db.restaurants.find(query)
    result = []
    for restaurant in restaurants:
        compute_average_rating(restaurant)
        if min_rating is not None:
            if restaurant['average_rating'] is None or restaurant['average_rating'] < min_rating:
                continue
        result.append(restaurant)
    return result

# Menambahkan restoran baru
@app.route('/add_restaurant', methods=['GET', 'POST'])
def add_restaurant():
    if "user_id" not in session:  # Cek apakah sudah login
        return redirect(url_for("login"))

    # Ambil kategori yang ada untuk dropdown
    categories = []
    if db:
        categories = db.restaurants.distinct("category")
    if not categories:
        categories = ["Indonesian", "Chinese", "Western", "Japanese", "Fast Food", "Cafe", "Other"]

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        address = request.form['address']
        try:
            latitude = float(request.form['latitude'])
            longitude = float(request.form['longitude'])
            if not (-90 <= latitude <= 90):
                flash('Latitude harus antara -90 dan 90', 'danger')
                return render_template('add_restaurant.html')
            if not (-180 <= longitude <= 180):
                flash('Longitude harus antara -180 dan 180', 'danger')
                return render_template('add_restaurant.html')
        except ValueError:
            flash('Koordinat tidak valid', 'danger')
            return render_template('add_restaurant.html')
        opening_hours = request.form.get('opening_hours')
        price_range = request.form.get('price_range')

        # Parsing harga numerik untuk filter
        price = None
        if price_range:
            import re
            nums = re.findall(r"\d+", price_range)
            if nums:
                price = float(nums[-1])

        # Menyimpan gambar restoran
        image_url = None
        if 'image' in request.files:
            image = request.files['image']
            if image and image.filename:
                filename = secure_filename(image.filename)
                file_path = os.path.join('static/uploads', filename)
                image.save(file_path)  # Menyimpan gambar di folder static/uploads
                # lakukan resize / crop agar ukurannya seragam
                process_image(file_path)
                image_url = f'/static/uploads/{filename}'  # URL gambar

        new_restaurant = {
            "name": name,
            "category": category,
            # "rating": rating,  # now computed from reviews
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "opening_hours": opening_hours,
            "price_range": price_range,
            "price": price,
            "image_url": image_url,
            "reviews": []
        }

        db.restaurants.insert_one(new_restaurant)
        flash("Restaurant added successfully!", "success")  # Pesan sukses
        print(f"Added restaurant: {new_restaurant}")  # Log data yang ditambahkan
        
        # Setelah menambah restoran, kembali ke halaman utama
        return redirect(url_for('index'))  # Redirect ke halaman utama setelah menambah restoran

        # Menyimpan gambar restoran
        image_url = None
        if 'image' in request.files:
            image = request.files['image']
            if image and image.filename:
                filename = secure_filename(image.filename)
                file_path = os.path.join('static/uploads', filename)
                image.save(file_path)  # Menyimpan gambar di folder static/uploads
                # lakukan resize / crop agar ukurannya seragam
                process_image(file_path)
                image_url = f'/static/uploads/{filename}'  # URL gambar

        new_restaurant = {
            "name": name,
            "category": category,
            "rating": rating,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "price_range": price_range,
            "price": price,
            "image_url": image_url,
            "reviews": []
        }

        db.restaurants.insert_one(new_restaurant)
        flash("Restaurant added successfully!", "success")  # Pesan sukses
        print(f"Added restaurant: {new_restaurant}")  # Log data yang ditambahkan
        
        # Setelah menambah restoran, kembali ke halaman utama
        return redirect(url_for('index'))  # Redirect ke halaman utama setelah menambah restoran

    return render_template('add_restaurant.html')  # Tampilkan halaman untuk menambahkan restoran

def is_admin():
    return session.get('username') == 'admin'


# Route untuk update restoran
@app.route('/edit_restaurant/<restaurant_id>', methods=['GET', 'POST'])
def edit_restaurant(restaurant_id):
    if "user_id" not in session:  # Cek jika pengguna belum login
        return redirect(url_for("login"))  # Arahkan ke halaman login
    if not is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('index'))

    # Ambil restoran berdasarkan ID dari MongoDB
    restaurant = db.restaurants.find_one({"_id": ObjectId(restaurant_id)})

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        address = request.form['address']
        opening_hours = request.form.get('opening_hours')

        # Update restoran di database
        db.restaurants.update_one(
            {"_id": ObjectId(restaurant_id)},
            {"$set": {"name": name, "category": category, "address": address, "opening_hours": opening_hours}}
        )
        flash("Restaurant updated successfully!", "success")
        return redirect(url_for('index'))

    return render_template('edit_restaurant.html', restaurant=restaurant)

# Route untuk delete restoran
@app.route('/delete_restaurant/<restaurant_id>', methods=['GET'])
def delete_restaurant(restaurant_id):
    if "user_id" not in session:
        return redirect(url_for("login"))  # Arahkan ke halaman login jika belum login
    if not is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('index'))

    # Hapus restoran berdasarkan ID
    db.restaurants.delete_one({"_id": ObjectId(restaurant_id)})
    flash("Restaurant deleted successfully!", "success")  # Tampilkan pesan sukses
    return redirect(url_for('index'))

# Route untuk menambahkan ulasan pada restoran
@app.route('/add_review/<restaurant_id>', methods=['GET', 'POST'])
def add_review(restaurant_id):
    if "user_id" not in session:  # Cek jika pengguna belum login
        return redirect(url_for("login"))

    if db is None:
        flash('Cannot add review: database unreachable', 'danger')
        return redirect(url_for('index'))

    # Ambil data restoran berdasarkan ID
    restaurant = db.restaurants.find_one({"_id": ObjectId(restaurant_id)})

    if request.method == 'POST':
        try:
            rating = float(request.form['rating'])
            comment = request.form['comment']

            # Menyimpan gambar ulasan
            if 'image' in request.files:
                image = request.files['image']
                if image and image.filename:
                    filename = secure_filename(image.filename)
                    file_path = os.path.join('static/uploads', filename)
                    image.save(file_path)  # Menyimpan gambar
                    process_image(file_path, size=(400,400))  # lebih kecil untuk review
                    image_url = f'/static/uploads/{filename}'
                else:
                    image_url = None
            else:
                image_url = None

            # Simpan ulasan ke MongoDB
            db.restaurants.update_one(
                {"_id": ObjectId(restaurant_id)},
                {"$push": {"reviews": {"user_id": session["user_id"], "username": session["username"], "rating": rating, "comment": comment, "image_url": image_url}}}
            )
            flash("Review added successfully!", "success")
            return redirect(url_for('restaurant_detail', restaurant_id=restaurant_id))  # Arahkan kembali ke halaman detail restoran
        except Exception as exc:
            app.logger.error("add review error: %s", exc)
            flash('Failed to add review, please try again later.', 'danger')
            return redirect(url_for('add_review', restaurant_id=restaurant_id))

    # Jika restoran tidak ada
    if not restaurant:
        flash('Restaurant not found', 'error')
        return redirect(url_for('index'))  # Arahkan ke halaman utama jika restoran tidak ditemukan

    # Kirim data restoran ke template untuk ditampilkan
    return render_template('add_review.html', restaurant=restaurant)

# Route untuk melihat detail restoran
@app.route('/restaurant/<restaurant_id>', methods=['GET'])
def restaurant_detail(restaurant_id):
    # Ambil data restoran berdasarkan ID dari MongoDB
    restaurant = restaurants_collection.find_one({"_id": ObjectId(restaurant_id)})

    if restaurant:
        compute_average_rating(restaurant)
        # Kirim data restoran ke template
        return render_template('restaurant_detail.html', restaurant=restaurant)
    else:
        # Jika restoran tidak ditemukan
        flash('Restaurant not found', 'error')
        return redirect(url_for('index'))  # Arahkan ke halaman utama

# Route untuk logout
@app.route('/logout')
def logout():
    session.clear()  # Menghapus semua data session (logout)
    # ubah kategori menjadi success agar warning box muncul dengan warna hijau
    flash('You have successfully logged out.', 'success')  # Menampilkan pesan logout sukses
    return redirect(url_for('login'))  # Arahkan kembali ke halaman login setelah logout

# Fungsi utama untuk menjalankan aplikasi Flask (hanya untuk development lokal)
if __name__ == '__main__':
    app.run(debug=True)