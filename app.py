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

# Konfigurasi Cloudinary
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

app = Flask(__name__, static_folder='static', static_url_path='/static')

UPLOAD_FOLDER = '/tmp'

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-cicipin-2024')


# =========================
# IMAGE PROCESSING
# =========================
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


# =========================
# DATABASE CONNECTION
# =========================
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


# =========================
# LOGIN
# =========================
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


# =========================
# REGISTER
# =========================
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


# =========================
# ADMIN CHECK
# =========================
def is_admin():
    return session.get("username") == "admin"


# =========================
# RATING CALCULATION
# =========================
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


# =========================
# OPEN STATUS
# =========================
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


# =========================
# SEARCH RESTAURANT
# =========================
def search_restaurants(search_term=None, min_rating=None, max_price=None):

    query = {}

    # filter kategori langsung
    if search_term and search_term.lower() != "semua":
        query['category'] = search_term

    restaurants = db.restaurants.find(query)

    result = []

    for restaurant in restaurants:

        compute_average_rating(restaurant)
        compute_open_status(restaurant)

        if min_rating is not None:
            if restaurant['average_rating'] is None or restaurant['average_rating'] < min_rating:
                continue

        result.append(restaurant)

    return result


# =========================
# HOME PAGE
# =========================
@app.route('/')
def index():

    if "user_id" not in session:
        return redirect(url_for("login"))

    # ambil kategori dari URL
    category = request.args.get("category")

    # ambil filter lain
    min_rating = request.args.get("min_rating")
    max_price = request.args.get("max_price")

    min_rating = float(min_rating) if min_rating else None
    max_price = float(max_price) if max_price else None

    restaurants = search_restaurants(category, min_rating, max_price)

    return render_template(
        'index.html',
        restaurants=restaurants,
        username=session["username"]
    )


# =========================
# ADD RESTAURANT
# =========================
@app.route('/add_restaurant', methods=['GET', 'POST'])
def add_restaurant():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if not is_admin():
        flash("Permission denied", "danger")
        return redirect(url_for("index"))

    if request.method == 'POST':

        name = request.form['name']
        category = request.form['category']
        address = request.form['address']

        latitude = float(request.form['latitude'])
        longitude = float(request.form['longitude'])

        opening_hours = request.form.get('opening_hours')
        price_range = request.form.get('price_range')

        image_url = None

        if 'image' in request.files:
            image = request.files['image']

            if image and image.filename:

                upload_result = cloudinary.uploader.upload(image)

                image_url = upload_result["secure_url"]

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

    return render_template('add_restaurant.html')


# =========================
# EDIT RESTAURANT
# =========================
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


# =========================
# DELETE RESTAURANT
# =========================
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


# =========================
# ADD REVIEW
# =========================
@app.route('/add_review/<restaurant_id>', methods=['GET', 'POST'])
def add_review(restaurant_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    restaurant = db.restaurants.find_one({"_id": ObjectId(restaurant_id)})

    if not restaurant:
        flash('Restaurant not found', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':

        rating = float(request.form['rating'])
        comment = request.form['comment']

        review_image = None

        review_image = None

        if 'image' in request.files:
            image = request.files['image']

            if image and image.filename:
                upload_result = cloudinary.uploader.upload(image)
                review_image = upload_result["secure_url"]

        db.restaurants.update_one(
            {"_id": ObjectId(restaurant_id)},
            {
                "$push": {
                    "reviews": {
                    "user_id": session["user_id"],
                    "username": session["username"],
                    "rating": rating,
                    "comment": comment,
                    "image_url": review_image
}
                }
            }
        )

        flash("Review added successfully!", "success")

        return redirect(url_for('restaurant_detail', restaurant_id=restaurant_id))

    return render_template('add_review.html', restaurant=restaurant)


# =========================
# RESTAURANT DETAIL
# =========================
@app.route('/restaurant/<restaurant_id>')
def restaurant_detail(restaurant_id):

    restaurant = restaurants_collection.find_one({
        "_id": ObjectId(restaurant_id)
    })

    if restaurant:

        compute_average_rating(restaurant)
        compute_open_status(restaurant)

        return render_template('restaurant_detail.html', restaurant=restaurant)

    flash('Restaurant not found', 'error')
    return redirect(url_for('index'))


# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():

    session.clear()

    flash('You have successfully logged out.', 'success')

    return redirect(url_for('login'))


# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    app.run(debug=True)