from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import os
import time
from flask import send_from_directory
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import send_from_directory
app = Flask(__name__)
app.secret_key = 'your_secret_key'

app.config['UPLOAD_FOLDER'] = os.path.join('uploads', 'symptoms')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="telemedicine",
        port=3306
    )



# User routes
@app.route('/')
def home():
    session.clear()
    return render_template('user/index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        # Connect to the database
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user_email = cursor.fetchone()

        if existing_user_email:
            # If email already exists, show an error message
            flash("Email already exists. Please try another one.", "error")
            connection.close()
            return redirect(url_for('signup'))

        # Check if the username already exists
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user_username = cursor.fetchone()

        if existing_user_username:
            # If username already exists, show an error message
            flash("Username already exists. Please choose another one.", "error")
            connection.close()
            return redirect(url_for('signup'))

        # Insert new user into the database if both username and email are unique
        cursor.execute("""
            INSERT INTO users (username, name, email, password) 
            VALUES (%s, %s, %s, %s)
        """, (username, name, email, password))
        connection.commit()
        
        cursor.close()
        connection.close()

        flash("Signup successful! Please log in.", "success")
        return redirect(url_for('login'))
    
    return render_template('user/signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username_or_email']
        password = request.form['password']
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username_or_email, username_or_email))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['username']
            flash("Logged in successfully!", "success")
            return redirect(url_for('user_dashboard'))
        else:
            flash("Invalid username/email or password", "danger")
    return render_template('user/login.html')

@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' in session:
        return render_template('user/user_dashboard.html', user_name=session['user_name'])
    else:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

@app.route('/view_prescriptions')
def view_prescriptions():
    if 'user_id' in session:
        return render_template('user/view_past_appointments.html')
    else:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

@app.route('/view_prescription/<int:appointment_id>')
def view_prescription(appointment_id):
    if 'user_id' not in session:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

    connection = get_db_connection()

    try:
        # Create a cursor to execute the query
        cursor = connection.cursor(dictionary=True)

        # Fetch prescription details along with patient information from appointments table
        cursor.execute("""
            SELECT 
                prescriptions.id AS prescription_id,
                prescriptions.doctor_name,
                prescriptions.date,
                prescriptions.details,
                appointments.name AS patient_name,
                appointments.age
            FROM 
                prescriptions
            INNER JOIN 
                appointments ON prescriptions.appointment_id = appointments.id
            WHERE 
                prescriptions.appointment_id = %s
        """, (appointment_id,))

        # Fetch the result
        prescription = cursor.fetchone()

        # If no prescription is found, show an error message
        if not prescription:
            flash("No prescription found for this appointment", "danger")
            return redirect(url_for('view_past_appointments'))

        # Close the cursor
        cursor.close()

    except mysql.connector.Error as err:
        flash(f"Error fetching prescription details: {err}", "danger")
        prescription = None
    finally:
        connection.close()  # Ensure the connection is closed after query execution

    # Return the prescription details to the template
    return render_template('user/view_prescription.html', prescription=prescription)


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for('home'))

@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if 'user_id' not in session:
        flash("Please log in to book an appointment", "warning")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Extract form data
        name = request.form.get('name')
        email = request.form.get('email')
        age = request.form.get('age')
        appointment_date = request.form.get('appointment_date')
        appointment_time = request.form.get('appointment_time')
        reason = request.form.get('reason')

        # Validate required fields
        if not all([name, email, age, appointment_date, appointment_time, reason]):
            flash("Please fill all the fields", "warning")
            return redirect(url_for('book_appointment'))

        # Handle symptom image upload
        symptom_img = None
        if 'symptom_img' in request.files:
            file = request.files['symptom_img']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = str(int(time.time())) + "_" + filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                symptom_img = unique_filename

        # Save appointment to the database
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            # Insert appointment record
            cursor.execute("""
                INSERT INTO appointments 
                (user_id, name, email, age, appointment_date, appointment_time, reason, symptom_img, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'requested')
            """, (session['user_id'], name, email, age, appointment_date, appointment_time, reason, symptom_img))
            connection.commit()

            # Update request_count for the user
            cursor.execute("""
                UPDATE users
                SET request_count = request_count + 1
                WHERE id = %s
            """, (session['user_id'],))  # Use session['user_id'] to refer to the logged-in user
            connection.commit()

            flash("Appointment requested successfully!", "success")

        except mysql.connector.Error as err:
            flash(f"Error booking appointment: {err}", "danger")
        finally:
            cursor.close()
            connection.close()

        return redirect(url_for('view_upcoming_appointments'))

    return render_template('user/book_appointment.html')


# Route to view upcoming appointments
@app.route('/view_appointments')
def view_appointments():
    if 'user_id' not in session:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch upcoming appointments for the logged-in user
        current_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT * FROM appointments 
            WHERE user_id = %s AND appointment_date >= %s
            ORDER BY appointment_date, appointment_time
        """, (user_id, current_date))
        upcoming_appointments = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f"Error fetching appointments: {err}", "danger")
        upcoming_appointments = []
    finally:
        cursor.close()
        connection.close()

    return render_template('user/view_upcoming_appointments.html', appointments=upcoming_appointments)


@app.route('/view_upcoming_appointments')
def view_upcoming_appointments():
    if 'user_id' not in session:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch upcoming appointments along with Jitsi links
        cursor.execute("""
            SELECT id, appointment_date, appointment_time, status, jitsi_link
            FROM appointments
            WHERE user_id = %s 
              AND TIMESTAMP(appointment_date, appointment_time) > NOW() - INTERVAL 5 MINUTE
            ORDER BY appointment_date, appointment_time
        """, (user_id,))

        appointments = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f"Error fetching upcoming appointments: {err}", "danger")
        appointments = []
    finally:
        cursor.close()
        connection.close()

    # Pass appointments to the template
    return render_template('user/view_upcoming_appointments.html', appointments=appointments)


@app.route('/view_past_appointments')
def view_past_appointments():
    if 'user_id' not in session:
        flash("Please log in to access this page", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch only past appointments with associated prescription details
        cursor.execute("""
            SELECT a.id, a.appointment_date, a.appointment_time, a.status, p.details 
            FROM appointments a
            LEFT JOIN prescriptions p ON a.id = p.appointment_id
            WHERE a.user_id = %s
              AND TIMESTAMP(a.appointment_date, a.appointment_time) <= NOW() - INTERVAL 5 MINUTE
            ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """, (user_id,))
        appointments = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f"Error fetching past appointments: {err}", "danger")
        appointments = []
    finally:
        cursor.close()
        connection.close()

    return render_template('user/view_past_appointments.html', appointments=appointments)

@app.route('/start_video_conference/<int:appointment_id>')
def start_video_conference(appointment_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch the Jitsi link for the given appointment ID
        cursor.execute("""
            SELECT jitsi_link FROM appointments WHERE id = %s
        """, (appointment_id,))
        result = cursor.fetchone()
    except mysql.connector.Error as err:
        flash(f"Error starting video conference: {err}", "danger")
        result = None
    finally:
        cursor.close()
        connection.close()

    if result and result['jitsi_link']:
        return redirect(f'https://meet.jit.si/{result["jitsi_link"]}')
    else:
        flash("No Jitsi link found for this appointment", "danger")
        return redirect(url_for('view_upcoming_appointments'))


@app.route('/download_prescription/<filename>')
def download_prescription(filename):
    # Ensure the file exists in the correct folder
    return send_from_directory(
        'uploads/prescriptions',  # Folder where the prescriptions are stored
        filename,                  # The file to send
        as_attachment=True         # Force download
    )




if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
