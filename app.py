import os
from dotenv import load_dotenv

load_dotenv()

import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime
import math

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

app = Flask(__name__, static_folder="static", static_url_path="/static")

UPLOAD_FOLDER = "/tmp"

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-cicipin-2024')


def process_image(path, size=(600,400)):
    try:
        img = Image.open(path)
        img = img.convert('RGB')
        img.thumbnail((size[0], size[1]), Image.ANTIALIAS)

        new_img = Image.new('RGB', size, (255,255,255))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        new_img.paste(img, (x, y))
        new_img.save(path)

    except Exception as e:
        app.logger.warning("failed to process image %s: %s", path, e)

try:
    client = MongoClient(os.environ.get("MONGODB_URI"), serverSelectionTimeoutMS=5000)
    db = client[os.environ.get("DB_NAME")]
    client.admin.command('ping')
    restaurants_collection = db["restaurants"]

except Exception as exc:
    import logging
    logging.getLogger(__name__).error("Database connection failed: %s", exc)
    client = None
    db = None
    restaurants_collection = None

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        if db is None:
            flash('Cannot log in: database unreachable', 'danger')
            return render_template('login.html')

        user = db.users.find_one({"username": username})

        if user and check_password_hash(user['password'], password):

            session['user_id'] = str(user['_id'])
            session['username'] = username

            flash('You have successfully logged in', 'success')
            return redirect(url_for('index'))

        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():

    if "user_id" in session:
        return redirect(url_for('index'))

    if request.method == 'POST':

        if db is None:
            flash('Cannot register: database unreachable', 'danger')
            return redirect(url_for('register'))

        username = request.form['username']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        existing_user = db.users.find_one({"username": username})

        if existing_user:
            flash("Username already exists", "danger")
            return redirect(url_for('register'))

        db.users.insert_one({
            "username": username,
            "password": hashed_password
        })

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

def is_admin():
    return session.get("username") == "admin"

def compute_average_rating(restaurant):

    reviews = restaurant.get('reviews', [])

    if reviews:
        try:
            avg = sum(r.get('rating', 0) for r in reviews) / len(reviews)
        except Exception:
            avg = 0

        restaurant['average_rating'] = round(avg, 1)

    else:
        restaurant['average_rating'] = None

    return restaurant

def compute_open_status(restaurant):

    opening_hours = restaurant.get("opening_hours")

    if not opening_hours:
        restaurant["is_open"] = None
        return restaurant

    try:

        open_time, close_time = opening_hours.split("-")

        now = datetime.now().time()

        open_time = datetime.strptime(open_time.strip(), "%H:%M").time()
        close_time = datetime.strptime(close_time.strip(), "%H:%M").time()

        restaurant["is_open"] = open_time <= now <= close_time

    except:
        restaurant["is_open"] = None

    return restaurant

# --- FITUR BARU: FUNGSI MENGHITUNG JARAK ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Radius bumi dalam kilometer
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- REVISI: DITAMBAHKAN PARAMETER FILTER ---
def search_restaurants(search_term=None, min_rating=None, max_price=None, sort_by=None, user_lat=None, user_lon=None):

    query = {}

    if search_term and search_term.lower() != "semua":
        query['category'] = search_term

    restaurants = db.restaurants.find(query)

    result = []

    for restaurant in restaurants:

        compute_average_rating(restaurant)
        compute_open_status(restaurant)

        # Hitung jumlah review untuk filter Terlaris
        restaurant['review_count'] = len(restaurant.get('reviews', []))

        # Hitung jarak jika koordinat user berhasil diambil dari browser
        if user_lat and user_lon and restaurant.get('latitude') and restaurant.get('longitude'):
            restaurant['distance'] = haversine(float(user_lat), float(user_lon), float(restaurant['latitude']), float(restaurant['longitude']))
            restaurant['distance_str'] = f"{restaurant['distance']:.1f} km"
        else:
            restaurant['distance'] = float('inf')
            restaurant['distance_str'] = ""

        if min_rating is not None:
            if restaurant['average_rating'] is None or restaurant['average_rating'] < min_rating:
                continue

        result.append(restaurant)

    # Logika Pengurutan (Sorting / Filter)
    if sort_by == 'rating':
        result.sort(key=lambda x: x.get('average_rating') or 0, reverse=True)
    elif sort_by == 'terlaris':
        result.sort(key=lambda x: x.get('review_count') or 0, reverse=True)
    elif sort_by == 'jarak' and user_lat and user_lon:
        result.sort(key=lambda x: x.get('distance'))

    return result


@app.route('/')
def index():

    category = request.args.get("category")

    min_rating = request.args.get("min_rating")
    max_price = request.args.get("max_price")

    # REVISI: Ambil parameter dari URL untuk Filter
    sort_by = request.args.get("sort_by")
    user_lat = request.args.get("user_lat")
    user_lon = request.args.get("user_lon")

    min_rating = float(min_rating) if min_rating else None
    max_price = float(max_price) if max_price else None

    # REVISI: Masukkan parameter sort ke pencarian
    restaurants = search_restaurants(category, min_rating, max_price, sort_by, user_lat, user_lon)

    saved_restaurant_ids = []
    username = None
    is_authenticated = False

    if "user_id" in session:
        is_authenticated = True
        username = session.get("username")
        user_wishlist = list(db.wishlists.find({"user_id": session["user_id"]}))
        saved_restaurant_ids = [str(w["restaurant_id"]) for w in user_wishlist]

    return render_template(
        'index.html',
        restaurants=restaurants,
        username=username,
        saved_restaurant_ids=saved_restaurant_ids,
        sort_by=sort_by,
        is_authenticated=is_authenticated
    )


@app.route('/add_restaurant', methods=['GET', 'POST'])
def add_restaurant():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if not is_admin():
        flash("Permission denied", "danger")
        return redirect(url_for("index"))

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category = request.form.get('category')
            address = request.form.get('address')

            latitude = float(request.form.get('latitude'))
            longitude = float(request.form.get('longitude'))

            opening_hours = request.form.get('opening_hours')
            price_range = request.form.get('price_range')

            image_url = None

            image = request.files.get("image")

            if image and image.filename != "":
                try:
                    upload_result = cloudinary.uploader.upload(image)
                    image_url = upload_result["secure_url"]
                    print("UPLOAD SUCCESS:", image_url)
                except Exception as e:
                    print("CLOUDINARY ERROR:", e)

            new_restaurant = {
                "name": name,
                "category": category,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "opening_hours": opening_hours,
                "price_range": price_range,
                "image_url": image_url,
                "reviews": []
            }

            db.restaurants.insert_one(new_restaurant)

            flash("Restaurant added successfully!", "success")
            return redirect(url_for('index'))

        except Exception as e:
            print("ADD RESTAURANT ERROR:", e)
            flash("Failed to add restaurant", "danger")
            return redirect(url_for('add_restaurant'))

    return render_template('add_restaurant.html')


@app.route('/edit_restaurant/<restaurant_id>', methods=['GET', 'POST'])
def edit_restaurant(restaurant_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if not is_admin():
        flash("Permission denied", "danger")
        return redirect(url_for("index"))

    restaurant = db.restaurants.find_one({"_id": ObjectId(restaurant_id)})

    if request.method == 'POST':

        name = request.form['name']
        category = request.form['category']
        address = request.form['address']
        opening_hours = request.form.get('opening_hours')

        db.restaurants.update_one(
            {"_id": ObjectId(restaurant_id)},
            {"$set": {
                "name": name,
                "category": category,
                "address": address,
                "opening_hours": opening_hours
            }}
        )

        flash("Restaurant updated successfully!", "success")
        return redirect(url_for('index'))

    return render_template('edit_restaurant.html', restaurant=restaurant)

@app.route('/delete_restaurant/<restaurant_id>')
def delete_restaurant(restaurant_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if not is_admin():
        flash("Permission denied", "danger")
        return redirect(url_for("index"))

    db.restaurants.delete_one({"_id": ObjectId(restaurant_id)})

    flash("Restaurant deleted successfully!", "success")

    return redirect(url_for('index'))


@app.route('/add_review/<restaurant_id>', methods=['GET', 'POST'])
def add_review(restaurant_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    restaurant = db.restaurants.find_one({"_id": ObjectId(restaurant_id)})

    if not restaurant:
        flash('Restaurant not found', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':

        rating = float(request.form.get('rating', 0))
        comment = request.form['comment']

        review_image = None

        if 'image' in request.files:
            image = request.files['image']

            if image and image.filename:
                try:
                    upload_result = cloudinary.uploader.upload(
                        image,
                        resource_type="image"
                    )
                    review_image = upload_result["secure_url"]
                except Exception as e:
                    app.logger.error(f"Cloudinary review upload failed: {e}")

        db.restaurants.update_one(
            {"_id": ObjectId(restaurant_id)},
            {
                "$push": {
                    "reviews": {
                        "user_id": session["user_id"],
                        "username": session["username"],
                        "rating": rating,
                        "comment": comment,
                        "image_url": review_image,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                }
            }
        )

        flash("Review added successfully!", "success")

        return redirect(url_for('restaurant_detail', restaurant_id=restaurant_id))

    return render_template('add_review.html', restaurant=restaurant)


@app.route('/restaurant/<restaurant_id>')
def restaurant_detail(restaurant_id):

    if restaurants_collection is None:
        flash('Database connection failed', 'danger')
        return redirect(url_for('index'))

    restaurant = restaurants_collection.find_one({
        "_id": ObjectId(restaurant_id)
    })

    if restaurant:

        compute_average_rating(restaurant)
        compute_open_status(restaurant)

        return render_template(
            'restaurant_detail.html',
            restaurant=restaurant,
            username=session.get('username'),
            is_authenticated="user_id" in session
        )

    flash('Restaurant not found', 'error')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():

    session.clear()

    flash('You have successfully logged out.', 'success')

    return redirect(url_for('login'))


# --- FITUR BARU: ROUTE UNTUK MENYIMPAN TO-GO LIST ---
@app.route('/toggle_wishlist', methods=['POST'])
def toggle_wishlist():
    if "user_id" not in session:
        return {"success": False, "message": "Unauthorized"}, 401

    data = request.json
    restaurant_id = data.get("restaurant_id")

    existing = db.wishlists.find_one({"user_id": session["user_id"], "restaurant_id": ObjectId(restaurant_id)})

    if existing:
        db.wishlists.delete_one({"_id": existing["_id"]})
        is_saved = False
    else:
        db.wishlists.insert_one({"user_id": session["user_id"], "restaurant_id": ObjectId(restaurant_id)})
        is_saved = True

    return {"success": True, "is_saved": is_saved}


# --- FITUR BARU: ROUTE UNTUK HALAMAN DAFTAR TO-GO LIST ---
@app.route('/wishlist')
def wishlist():
    if "user_id" not in session:
        return redirect(url_for("login"))

    wishlist_docs = list(db.wishlists.find({"user_id": session["user_id"]}))
    restaurant_ids = [w["restaurant_id"] for w in wishlist_docs]

    restaurants = list(db.restaurants.find({"_id": {"$in": restaurant_ids}}))

    for r in restaurants:
        compute_average_rating(r)
        compute_open_status(r)

    saved_restaurant_ids = [str(i) for i in restaurant_ids]

    return render_template('wishlist.html', restaurants=restaurants, username=session["username"], saved_restaurant_ids=saved_restaurant_ids)


if __name__ == '__main__':
    app.run(debug=True)
