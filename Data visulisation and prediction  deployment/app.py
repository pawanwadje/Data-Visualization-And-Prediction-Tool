from flask import Flask, abort, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_pymongo import PyMongo
from bson import ObjectId
from functools import wraps
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LinearRegression
import io
import uuid
import pytz
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Email
from flask_mail import Mail, Message

import os


india_tz = pytz.timezone("Asia/Kolkata")

# Import custom helper functions for data processing and visualization
from help_fun import load_csv_to_dataframe, clean_dataframe, infer_column_kinds, build_figure

# Initialize Flask application
app = Flask(__name__)

# -------------------- MongoDB Setup --------------------
# Configure MongoDB connection using environment variable with fallback for local development
uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/default_db")
app.config["MONGO_URI"] = uri

# Initialize PyMongo and set up database collections
mongo = PyMongo(app)
db = mongo.db
users_collection = db["users"]  # Collection for user accounts
charts_collection = db["charts"]  # Collection for saved charts
contacts_collection = db["contacts"]  # Collection for contact form submissions

# -------------------- Flask-Mail Setup --------------------
# Set secret key for session management and CSRF protection
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# Configure Flask-Mail for sending email notifications using environment variables
# Uses Gmail SMTP with TLS (port 587) by default
app.config.update(
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),  # Email server address
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),  # Port for email server
    MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true',  # Enable TLS encryption
    MAIL_USE_SSL=os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true',  # Enable SSL encryption
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),  # Email account username
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),  # Email account password or app-specific password
)
# Initialize Flask-Mail extension
mail = Mail(app)

# Define Flask-WTF form for contact page with validation
# This form includes fields for name, email, subject, and message with appropriate validators
class ContactForm(FlaskForm):
    # Field for user's full name with required validation
    name = StringField('Full Name', validators=[DataRequired()])
    # Field for user's email with required and email format validation
    email = StringField('Email', validators=[DataRequired(), Email()])
    # Field for message subject with required validation
    subject = StringField('Subject', validators=[DataRequired()])
    # Field for message content with required validation
    message = TextAreaField('Message', validators=[DataRequired()])

# -------------------- Session / Login Helpers --------------------
# Decorator function to require authentication for specific routes
# Redirects unauthenticated users to login page with flash message
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in by verifying session contains user info
        if "user" not in session:
            flash("Please login first!", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# -------------------- Authentication --------------------
# Route for user registration - handles both GET (display form) and POST (process registration)
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get email from form submission
        email = request.form["email"]
        # Check if user with this email already exists in database
        if users_collection.find_one({"email": email}):
            flash("Email already exists! Please login.", "danger")
            return redirect(url_for("login"))

        # Create new user with hashed password and save to database
        users_collection.insert_one({
            "name": request.form["name"],
            "email": email,
            "work": request.form.get("work", ""),
            "password": generate_password_hash(request.form["password"])
        })
        flash("Account registered successfully!", "success")
        return redirect(url_for("login"))
    # Render registration form for GET requests
    return render_template("register.html")

# Route for user login - handles both GET (display form) and POST (process login)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Get credentials from form submission
        email = request.form["email"]
        password = request.form["password"]
        # Find user in database by email
        user = users_collection.find_one({"email": email})
        # Verify password using hash comparison
        if user and check_password_hash(user["password"], password):
            # Store user ID in session to maintain login state
            session["user"] = str(user["_id"])
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials!", "danger")
    # Render login form for GET requests
    return render_template("login.html")

# Route for user logout - clears session and redirects to home page
@app.route("/logout")
@login_required
def logout():
    # Clear all session data to log out user
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for("index"))

# -------------------- Profile --------------------
# Route for user profile page - displays user information and saved charts
@app.route("/profile")
@login_required
def profile():
    # Get the currently logged-in user from database using session ID
    user = users_collection.find_one({"_id": ObjectId(session["user"])})
    # Find all charts linked to this user's email
    user_charts_doc = charts_collection.find_one({"email": user["email"]})
    
    # Convert embedded chart objects into a list for template rendering
    charts = []
    if user_charts_doc and "charts" in user_charts_doc:
        # Create chart list with ID and data for display
        charts = [
            {"id": chart_id, **chart_data}
            for chart_id, chart_data in user_charts_doc["charts"].items()
        ]
    
    # Render profile template with user data and charts
    return render_template("profile.html", user=user, charts=charts)








# Route for editing user profile - handles both GET (display form) and POST (update profile)
@app.route("/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    # Get logged-in user from database
    user = users_collection.find_one({"_id": ObjectId(session["user"])})
    if request.method == "POST":
        # Create update data dictionary from form fields
        update_data = {
            "name": request.form.get("name"),
            "work": request.form.get("work"),
        }

        # Update user document in database with new information
        users_collection.update_one({"_id": user["_id"]}, {"$set": update_data})
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))
    # Render edit profile form for GET requests
    return render_template("edit_profile.html", user=user)


# Route for password reset - handles both GET (display form) and POST (reset password)
@app.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        # Get email and new password from form
        email = request.form["email"]
        new_password = generate_password_hash(request.form["new_password"])
        # Update user's password in database with hashed new password
        users_collection.update_one({"email": email}, {"$set": {"password": new_password}})
        flash("Password updated successfully!", "success")
        return redirect(url_for("login"))
    # Render forgot password form for GET requests
    return render_template("forgot.html")

# -------------------- Contact --------------------
# Contact form route - handles both GET (display form) and POST (process contact submission)
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    # Create an instance of the contact form
    form = ContactForm()
    if request.method == 'POST':
        try:
            # Save contact information to MongoDB database
            contact_entry = {
                "name": request.form['name'],
                "email": request.form['email'],
                "subject": request.form['subject'],
                "reason": request.form.get('reason'),
                "phone": request.form.get('phone'),
                "company": request.form.get('company'),
                "message": request.form['message']
            }
            contacts_collection.insert_one(contact_entry)

            # Send notification email to admin using Flask-Mail
            msg = Message(
                subject=f"New Contact: {request.form['subject']}",
                sender=os.environ.get('MAIL_USERNAME'),
                recipients=[os.environ.get('ADMIN_EMAIL')],
                body=f"""
                    Name: {request.form['name']}
                    Email: {request.form['email']}
                    Reason: {request.form.get('reason')}
                    Phone: {request.form.get('phone')}
                    Company: {request.form.get('company')}
                    Message: {request.form['message']}
                                    """
            )
            mail.send(msg)

            # Return success response as JSON
            return jsonify({'status': 'success', 'message': 'Contact Request sent successfully!'})
        except Exception as e:
            # Log error and return failure response
            print(e)
            return jsonify({'status': 'error', 'message': 'Failed to send Contact Request.'})

    # Render contact form template for GET requests
    return render_template('contact.html', form=form)

# -------------------- Global Variables --------------------
# Global storage for dataframes during session
DATAFRAMES = {}
# Global variable to store the trained machine learning model
model = None
# Dictionary to store label encoders for categorical variables
le_dict = {}
# Variable to store the target column name for prediction
target=None

# -------------------- Dashboard --------------------
# Home page route - displays the main index page
@app.route("/")
def index():
    return render_template("index.html")

# Prediction dashboard route - requires authentication
@app.route("/prediction_dashboard")
@login_required
def prediction_dashboard():
    return render_template("prediction_dashboard.html")

# Data visualization dashboard route - requires authentication
@app.route("/visualize_dashboard")
@login_required
def visualize_dashboard():
    return render_template("visualize_dashboard.html")


# Route to handle file upload for data analysis - accepts CSV, XLS, and XLSX files
@app.route("/upload_file", methods=["POST"])
def upload_file():
    try:
        # Get uploaded file from request
        file = request.files.get("file")
        if not file:
            return jsonify(error="No file selected"), 400

        # Process file based on extension
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file)
        elif file.filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(file)
        else:
            return jsonify(error="Invalid file type."), 400

        # Validate that the file is not empty
        if df.empty:
            return jsonify(error="The uploaded file is empty"), 400

        # Store the dataframe in global storage for further processing
        DATAFRAMES["latest"] = df

        # Extract and analyze column information for UI display
        columns = df.columns.tolist()
        column_info = {}
        for col in columns:
            # Gather metadata for each column to help with data analysis
            column_info[col] = {
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "unique_count": int(df[col].nunique()),
                "sample_values": df[col].dropna().head(3).astype(str).tolist(),
                "is_numerical": pd.api.types.is_numeric_dtype(df[col]),
                "is_date": pd.api.types.is_datetime64_any_dtype(df[col]),
                "unique_values": df[col].dropna().unique().astype(str).tolist()[:10],
            }

        # Return column information and success message as JSON
        return jsonify({
            "columns": columns,
            "column_info": column_info,
            "shape": df.shape,
            "message": f"File uploaded successfully! Found {len(columns)} columns and {df.shape[0]} rows."
        })
    except Exception as e:
        # Return error message if processing fails
        return jsonify(error=str(e)), 500


# Route to train machine learning model - processes uploaded data and creates predictive model
@app.route("/train", methods=["POST"])
def train_model():
    # Update global variables to store the trained model and label encoders
    global model, le_dict,target
    try:
        # Get target column and feature columns from form data
        target = request.form.get("target")
        features = request.form.getlist("features[]")
        if not target or not features:
            return jsonify(error="Select target and features."), 400
        if target in features:
            return jsonify(error="Target cannot be in features."), 400

        # Verify that data has been uploaded
        if "latest" not in DATAFRAMES:
            return jsonify(error="No data uploaded."), 400

        # Create a copy of the dataframe to avoid modifying the original
        df = DATAFRAMES["latest"].copy()
        # Initialize label encoder dictionary
        le_dict = {}

        # Handle missing values in features and target columns
        for col in features + [target]:
            if df[col].dtype == "object":
                # Fill categorical columns with mode or 'Unknown'
                df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else "Unknown")
            else:
                # Fill numerical columns with median
                df[col] = df[col].fillna(df[col].median())

        # Encode categorical variables using LabelEncoder
        for col in features + [target]:
            if df[col].dtype == "object":
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                # Store encoder for later use in prediction
                le_dict[col] = le

        # Prepare feature matrix (X) and target vector (y)
        X = df[features]
        y = df[target]
        # Train Linear Regression model
        model = LinearRegression().fit(X, y)
        # Calculate R-squared score to measure model performance
        r2_score = model.score(X, y)

        # Return training results and model performance metrics
        return jsonify({
            "message": "Model trained successfully!",
            "r2_score": round(r2_score, 4),
            "sample_count": len(df),
            "feature_count": len(features)
        })
    except Exception as e:
        # Return error message if training fails
        return jsonify(error=str(e)), 500


# Route to make predictions using the trained model
@app.route("/predict", methods=["POST"])
def predict():
    # Access global variables containing the trained model and encoders
    global model, le_dict,target

    try:
        # Verify that a model has been trained
        if model is None:
            return jsonify(error="No model trained."), 400

        # Get input data from request JSON
        data = request.get_json()
        # Convert input data to DataFrame for prediction
        df_input = pd.DataFrame([data])

        # Apply label encoding to categorical columns using stored encoders
        for col in df_input.columns:
            if col in le_dict:
                le = le_dict[col]
                # Handle unseen categories by using the first class
                df_input[col] = df_input[col].astype(str).apply(lambda x: x if x in le.classes_ else le.classes_[0])
                # Transform the categorical values using the encoder
                df_input[col] = le.transform(df_input[col])

        # Make prediction using the trained model
        prediction = model.predict(df_input[model.feature_names_in_])[0]

        # Return prediction result
        return jsonify({
            "target": target,
            "prediction": round(float(prediction), 4),
            "message": "Prediction successful!"
        })
    except Exception as e:
        # Return error message if prediction fails
        return jsonify(error=str(e)), 500

# -------------------- Chart Visualization --------------------
# Route to handle CSV file upload for chart creation
@app.route("/upload", methods=["POST"])
def upload():
    # Get uploaded file from request
    file = request.files.get("file")
    if not file:
        flash("Please select a CSV file.")
        return redirect(url_for("index"))
    try:
        # Load and clean the CSV data
        df = clean_dataframe(load_csv_to_dataframe(file))
        # Generate unique ID for this upload
        upload_id = str(uuid.uuid4())
        # Store the dataframe for further processing
        DATAFRAMES[upload_id] = df
        # Redirect to configuration page with upload ID
        return redirect(url_for("configure", upload_id=upload_id))
    except Exception as e:
        flash(f"Failed to read CSV: {e}")
        return redirect(url_for("index"))

# Route to configure chart properties - handles both GET (display form) and POST (process configuration)
@app.route("/configure/<upload_id>", methods=["GET", "POST"])
@login_required
def configure(upload_id):
    # Get the dataframe associated with this upload ID
    df = DATAFRAMES.get(upload_id)
    if df is None:
        flash("Upload not found.")
        return redirect(url_for("index"))

    # Infer the data types of each column
    kinds = infer_column_kinds(df)
    # Define available chart types
    chart_types = [("line", "Line"), ("bar", "Bar"), ("pie", "Pie"),
                   ("scatter", "Scatter"), ("histogram", "Histogram"), ("box", "Box")]

    # Initialize variables for chart display
    fig_html = None
    selected = {"chart": "line", "x": None, "y": None, "color": None, "agg": None, "title": "", "palette": None}

    if request.method == "POST":
        # Get chart configuration from form
        chart_type = request.form.get("chart") or "line"
        x_col = request.form.get("x") or None
        y_col = request.form.get("y") or None
        title = request.form.get("title") or f"{chart_type} Chart"

        selected.update({"chart": chart_type, "x": x_col, "y": y_col, "title": title})

        try:
            # Build the chart figure using Plotly
            fig = build_figure(df, chart_type, x_col, y_col, title)
            # Convert figure to HTML for display
            fig_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            flash(f"Failed to build chart: {e}")

    # Render chart configuration template
    return render_template("configure.html", upload_id=upload_id, columns=list(df.columns),
                           kinds=kinds, chart_types=chart_types, fig_html=fig_html, selected=selected)

# Route to save a configured chart to the user's account
@app.route("/save_chart/<upload_id>", methods=["POST"])
@login_required
def save_chart(upload_id):
    # Get the dataframe associated with this upload ID
    df = DATAFRAMES.get(upload_id)
    if df is None:
        flash("Upload not found.")
        return redirect(url_for("index"))

    # Get the current user's email
    user_doc = users_collection.find_one(
        {"_id": ObjectId(session["user"])}
    )
    user_email = user_doc.get("email")

    # Get chart configuration from form
    chart_type = request.form.get("chart") or "line"
    x_col = request.form.get("x") or None
    y_col = request.form.get("y") or None
    title = request.form.get("title") or f"{chart_type.title()} Chart"

    try:
        # Build the chart figure using Plotly
        fig = build_figure(df, chart_type, x_col, y_col, title)

        # Convert chart to HTML snapshot for storage
        fig_html = fig.to_html(
            include_plotlyjs="cdn",
            full_html=False
        )

        # Create chart record with all necessary information
        chart_obj = {
            "name": title,
            "chart_type": chart_type,
            "x": x_col,
            "y": y_col,
            "chart_html": fig_html,   # Store HTML representation of chart
            "created_at": datetime.now(india_tz).strftime("%Y-%m-%d %H:%M:%S")  # Store creation timestamp in India timezone
        }

        # Save chart to user's collection in database
        user_chart_doc = charts_collection.find_one({"email": user_email})

        if user_chart_doc:
            # If user already has charts, add to existing collection
            charts = user_chart_doc.get("charts", {})
            chart_key = f"chart_{len(charts) + 1}"
            charts[chart_key] = chart_obj

            charts_collection.update_one(
                {"email": user_email},
                {"$set": {"charts": charts}}
            )
        else:
            # If user has no charts yet, create new collection
            charts_collection.insert_one({
                "email": user_email,
                "charts": {"chart_1": chart_obj}
            })

        flash(f"Chart '{title}' saved as record successfully ✔")
        return redirect(url_for("configure", upload_id=upload_id))

    except Exception as e:
        flash(f"Failed to save chart: {e}")
        return redirect(url_for("configure", upload_id=upload_id))

# Route to view a specific chart by ID - shows individual chart details
@app.route("/view_chart/<chart_id>")
@login_required
def view_chart(chart_id):
    # Fetch logged-in user from database using session ID
    user = users_collection.find_one({"_id": ObjectId(session["user"])})
    
    # Fetch charts document by user's email
    charts_doc = charts_collection.find_one({"email": user["email"]})
    if not charts_doc or "charts" not in charts_doc:
        # Return 404 if no charts found for user
        abort(404)
    
    # Find the requested chart by ID
    chart = charts_doc["charts"].get(chart_id)
    if not chart:
        # Return 404 if chart not found
        abort(404)
    
    # Render chart view template with chart data
    return render_template("view_chart.html", chart=chart, chart_id=chart_id)

# Route to delete a specific chart by ID - only accessible via POST request
@app.route("/delete_chart/<chart_id>", methods=["POST"])
@login_required
def delete_chart(chart_id):
    # Get logged-in user from database using session ID
    user = users_collection.find_one({"_id": ObjectId(session["user"])})
    if not user:
        # Return 401 if user not found
        abort(401)

    # Find user's chart document by email
    charts_doc = charts_collection.find_one({"email": user["email"]})
    if not charts_doc:
        # Return 404 if chart document not found
        abort(404)

    # Ensure chart exists before attempting to delete
    if chart_id not in charts_doc.get("charts", {}):
        flash("Chart not found.", "error")
        return redirect(url_for("profile"))

    # Remove the specific chart from user's charts using MongoDB $unset operator
    charts_collection.update_one(
        {"email": user["email"]},
        {"$unset": {f"charts.{chart_id}": ""}}
    )

    flash("Chart deleted successfully!", "success")
    return redirect(url_for("profile"))


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    # Log the error to console
    print(f"[ERROR] Internal server error: {e}")
    return render_template("500.html"), 500



# Main execution block - runs when script is executed directly
if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    # Run the Flask app in production mode
    app.run(host='0.0.0.0', port=port, debug=False)
