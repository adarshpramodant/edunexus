# EduNexus

A complete college ERP system with role-based access.

## Project Structure
- `backend/`: Python Flask REST API
- `frontend/`: HTML, CSS, JavaScript user interface
- `schema.sql`: PostgreSQL database schema (for Supabase)

## Setup Instructions

### 1. Database (Supabase)
1. Create a new Supabase project.
2. Go to the SQL Editor in Supabase.
3. Copy the contents of `schema.sql` and run it to create the required tables.
4. Get your standard PostgreSQL connection string from the Supabase Database settings.

### 2. Backend (Flask)
1. Open a terminal and navigate to the `backend` folder: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file from the example: `cp .env.example .env` (or rename it manually).
6. Edit `.env` and paste your Supabase PostgreSQL connection string as `DATABASE_URL`.
7. Run the Flask server: `python app.py`

### 3. Frontend
1. The frontend consists of static files.
2. You can open `frontend/index.html` directly in your browser.
3. For the best experience (to avoid CORS/file protocol issues), run a simple local server:
   - `cd frontend`
   - `python -m http.server 8000`
4. Open `http://localhost:8000` in your browser.

## Current Progress (Step 1)
- Supabase SQL Schema mapped out.
- Flask Backend set up with standard Postgres endpoints.
- Role-based signup and login UI with modern "Premium" glassmorphism SaaS style.
- JWT-based authentication system implemented.
