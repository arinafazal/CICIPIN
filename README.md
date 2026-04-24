# Cicipin - Restaurant Review App

Aplikasi web untuk menambah dan meninjau restoran dengan fitur user authentication dan admin controls.

## Fitur
- User registration & login dengan password hashing
- Tambah, edit, delete restoran (admin only)
- Tambah review dengan rating dan foto
- Search by name, category, atau address
- Image processing (resize & crop)
- Responsive design

## Setup Lokal

### 1. Clone Repository
```bash
git clone <your-repo>
cd CICIPIN
```

### 2. Setup Python Virtual Environment
```bash
python -m venv cicipinenv
cicipinenv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup Environment Variables
Copy `.env.example` ke `.env` dan isi dengan MongoDB credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=cicipin
SECRET_KEY=your-secret-key
```

### 5. Run Aplikasi
```bash
python app.py
```

Aplikasi akan running di `http://127.0.0.1:5000`

### Default Admin Account
Untuk membuat admin:
1. Register dengan username: `admin`
2. Login dan gunakan edit/delete features

## Deployment ke Vercel

### Prerequisites
- Vercel account (https://vercel.com)
- Git repository (GitHub, GitLab, atau Bitbucket)
- MongoDB Atlas account dengan connection string

### Steps

1. **Push code ke Git**
```bash
git add .
git commit -m "Ready for Vercel deployment"
git push origin main
```

2. **Deploy di Vercel**
   - Go to https://vercel.com
   - Click "New Project"
   - Import your Git repository
   - Vercel akan auto-detect Python project

3. **Setup Environment Variables di Vercel**
   - Project Settings → Environment Variables
   - Tambahkan:
     - `MONGODB_URI`: MongoDB Atlas connection string
     - `DB_NAME`: Database name (default: `cicipin`)
     - `SECRET_KEY`: Random secret key

4. **Configure MongoDB Atlas**
   - Go to MongoDB Atlas → Network Access
   - Tambah IP `0.0.0.0/0` untuk allow Vercel (atau specific Vercel IPs)
   - Pastikan IP whitelist allows connections from Vercel

5. **Deploy**
   - Vercel akan auto-build dan deploy
   - App URL akan ditampilkan di dashboard

## Struktur Project
```
CICIPIN/
├── api/
│   └── index.py          # Vercel handler
├── static/
│   ├── style.css
│   ├── script.js
│   └── uploads/          # User uploaded images
├── templates/            # HTML templates
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── add_restaurant.html
│   ├── edit_restaurant.html
│   ├── restaurant_detail.html
│   └── add_review.html
├── app.py               # Main Flask app
├── requirements.txt     # Python dependencies
├── vercel.json         # Vercel config
├── .env                # Environment variables (local only)
└── .vercelignore       # Files to ignore on deployment
```

## Known Limitations

### Image Uploads on Vercel
Vercel's serverless functions don't have persistent file storage. Uploaded images will be deleted between deployments. Solutions:
1. Use cloud storage (AWS S3, Google Cloud Storage, Cloudinary)
2. Store images as Base64 in MongoDB (limited size)
3. Use Vercel's Blob Storage (paid feature)

### Maps
Leaflet map integration is commented out due to JavaScript/Jinja conflicts. Can be re-enabled if needed.

## Troubleshooting

### "Serverless Function has crashed"
- Check Vercel logs: Project Settings → Deployments → View Logs
- Verify MongoDB connection string is correct
- Ensure MongoDB allows connections from Vercel IPs

### "Cannot log in: database unreachable"
- Check if MongoDB Atlas is online
- Verify MONGODB_URI env variable
- Check network access whitelist in MongoDB Atlas

### Missing Images on Vercel
- Upload images locally - they're stored in `/static/uploads/`
- For production, migrate to cloud storage

## Technologies Used
- **Backend**: Flask 3.1.3
- **Database**: MongoDB 4.16.0
- **Auth**: Werkzeug (password hashing)
- **Image Processing**: Pillow 10.2.0
- **Frontend**: HTML/CSS/JavaScript
- **Hosting**: Vercel (serverless Python)

## License
MIT

