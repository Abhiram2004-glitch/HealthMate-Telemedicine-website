from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import mysql.connector
import os
import random
import string
from werkzeug.utils import secure_filename
import datetime




# Create Flask app instance
app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join('uploads', 'prescriptions')

app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'jpg', 'jpeg', 'png'}
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'jpg', 'jpeg', 'png'}
# Generate a random string for the Jitsi meeting room
def generate_jitsi_link():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def regenerate_missing_jitsi_links():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Select approved appointments with missing jitsi links
    cursor.execute("""
        SELECT id FROM appointments WHERE status = 'approved' AND (jitsi_link IS NULL OR jitsi_link = '')
    """)
    appointments = cursor.fetchall()

    for appointment in appointments:
        appointment_id = appointment['id']
        jitsi_link = f"appointment-{appointment_id}"

        # Update the database with the new Jitsi link
        cursor.execute("""
            UPDATE appointments
            SET jitsi_link = %s
            WHERE id = %s
        """, (jitsi_link, appointment_id))

    connection.commit()
    cursor.close()
    connection.close()
    print("Missing Jitsi links regenerated successfully!")




# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="telemedicine",
        port=3306
    )

# Home route - Redirect to admin dashboard directly
@app.route('/')
def home():
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/regenerate_jitsi_links', methods=['POST'])
def admin_regenerate_jitsi_links():
    regenerate_missing_jitsi_links()
    return redirect(url_for('admin_dashboard'))


# Admin Dashboard
@app.route('/admin')
def admin_dashboard():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS count FROM appointments")
    total_appointments = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE status = 'requested'")
    pending_appointments = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE prescription_filename IS NOT NULL")
    prescriptions_uploaded = cursor.fetchone()['count']

    cursor.close()
    connection.close()

    return render_template(
        'admin/admin_dashboard.html',
        total_appointments=total_appointments,
        pending_appointments=pending_appointments,
        prescriptions_uploaded=prescriptions_uploaded
    )

@app.route('/admin/manage_appointments', methods=['GET', 'POST'])
def manage_appointments():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch distinct appointment dates for the filter
    cursor.execute("""
        SELECT DISTINCT DATE(appointment_date) AS appointment_date
        FROM appointments
        ORDER BY appointment_date ASC 
    """)
    date_options = cursor.fetchall()

    appointments = []
    selected_date = None

    if request.method == 'POST':
        # Retain the selected date from the form
        selected_date = request.form.get('appointment_date')

        # Handle prescription upload
        if 'upload_prescription' in request.form:
            appointment_id = request.form.get('appointment_id')
            if 'prescription_file' not in request.files or request.files['prescription_file'].filename == '':
                flash('No file selected', 'danger')
            else:
                file = request.files['prescription_file']
                if allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)

                    # Update the database with the prescription file path
                    cursor.execute("""
                        UPDATE appointments 
                        SET prescription_filename = %s 
                        WHERE id = %s
                    """, (filename, appointment_id))
                    connection.commit()
                    flash('Prescription uploaded successfully', 'success')

        # Fetch appointments for the selected date
        if selected_date:
            cursor.execute("""
                SELECT id, name, email, age, appointment_date, appointment_time, status, 
                       jitsi_link, reason, symptom_img, prescription_filename
                FROM appointments 
                WHERE DATE(appointment_date) = %s
                ORDER BY appointment_date DESC , appointment_time asc
            """, (selected_date,))
            appointments = cursor.fetchall()

    # Handle GET requests or fallback for invalid POST date
    if not selected_date:
        selected_date = datetime.datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT id, name, email, age, appointment_date, appointment_time, status, 
                   jitsi_link, reason, symptom_img, prescription_filename
            FROM appointments 
            WHERE DATE(appointment_date) = %s
            ORDER BY appointment_date DESC
        """, (selected_date,))
        appointments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'admin/manage_appointments.html',
        appointments=appointments,
        date_options=date_options,
        selected_date=selected_date,
        current_date=datetime.datetime.now().strftime('%Y-%m-%d')
    )


# Accept appointment
@app.route('/admin/accept_appointment/<int:appointment_id>', methods=['POST'])
def accept_appointment(appointment_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Automatically generate a unique Jitsi link
        jitsi_link = f"appointment-{appointment_id}-{generate_jitsi_link()}"

        # Update the appointment status and add the Jitsi link
        cursor.execute("""
            UPDATE appointments
            SET status = 'approved', jitsi_link = %s
            WHERE id = %s
        """, (jitsi_link, appointment_id))

        connection.commit()
        flash("Appointment approved successfully with a Jitsi link!", "success")

    except mysql.connector.Error as err:
        flash(f"Error approving appointment: {err}", "danger")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('manage_appointments'))





@app.route('/uploads/symptoms/<filename>')
def uploaded_file(filename):
    upload_folder = os.path.join(app.root_path, 'uploads', 'symptoms')
    return send_from_directory(upload_folder, filename)






# Decline Appointment
@app.route('/admin/decline_appointment/<int:appointment_id>', methods=['POST'])
def decline_appointment(appointment_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE appointments SET status = 'rejected' WHERE id = %s", (appointment_id,))
    connection.commit()
    cursor.close()
    connection.close()
    flash('Appointment declined successfully!', 'danger')
    return redirect(url_for('manage_appointments'))




# Admin Logout
@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash("Admin logged out successfully!", "success")
    return redirect(url_for('home'))

# Start Video Conference
@app.route('/start_video_conference/<int:appointment_id>')
def start_video_conference(appointment_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT jitsi_link FROM appointments WHERE id = %s
    """, (appointment_id,))
    jitsi_link = cursor.fetchone()
    cursor.close()
    connection.close()

    if jitsi_link:  # Now jitsi_link should be a dictionary
        return redirect(f'https://meet.jit.si/{jitsi_link["jitsi_link"]}')
    else:
        flash("No Jitsi link found for this appointment", "danger")
        return redirect(url_for('manage_appointments'))  # Redirect back to the manage appointments page





@app.route('/update_appointment_status/<int:appointment_id>/<string:action>', methods=['POST'])
def update_appointment_status(appointment_id, action):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if action == 'approve':
            # Automatically generate a unique Jitsi link
            jitsi_link = f"appointment-{appointment_id}-{generate_jitsi_link()}"  # Unique based on appointment ID

            # Update the appointment status and add the Jitsi link
            cursor.execute("""
                UPDATE appointments
                SET status = 'approved', jitsi_link = %s
                WHERE id = %s
            """, (jitsi_link, appointment_id))

            flash("Appointment approved successfully with a Jitsi link!", "success")

        elif action == 'decline':
            # Clear the Jitsi link if the appointment is declined
            cursor.execute("""
                UPDATE appointments
                SET status = 'declined', jitsi_link = NULL
                WHERE id = %s
            """, (appointment_id,))
            flash("Appointment declined successfully!", "warning")

        connection.commit()

    except mysql.connector.Error as err:
        flash(f"Error updating appointment status: {err}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('manage_appointments'))








@app.route('/admin/set_pending_appointment/<int:appointment_id>', methods=['POST'])
def set_pending_appointment(appointment_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Update the appointment status to 'pending'
        cursor.execute("""
            UPDATE appointments
            SET status = 'pending'
            WHERE id = %s
        """, (appointment_id,))
        
        connection.commit()
        flash("Appointment status set to pending!", "success")

    except mysql.connector.Error as err:
        flash(f"Error updating appointment status: {err}", "danger")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('manage_appointments'))



@app.route('/admin/view_users')
def view_users():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Fetch all users
    cursor.execute("SELECT id, name, email FROM users")
    users = cursor.fetchall()
    
    cursor.close()
    connection.close()
    return render_template('admin/view_users.html', users=users)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        # Delete the user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        connection.commit()

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        flash("User deleted successfully!", "success")
    except mysql.connector.Error as err:
        flash(f"Error deleting user: {err}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('view_users'))


@app.route('/search_user', methods=['GET'])
def search_user():
    query = request.args.get('query')
    if query:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            # Searching by name or email, similar to what you mentioned
            cursor.execute("SELECT * FROM users WHERE username LIKE %s OR email LIKE %s", (f"%{query}%", f"%{query}%"))
            users = cursor.fetchall()

            # Fetch additional details for each user
            user_details = []
            for user in users:
                cursor.execute("""
                    SELECT COUNT(*) AS appointment_count FROM appointments WHERE user_id = %s
                """, (user['id'],))
                appointment_count = cursor.fetchone()['appointment_count']

                cursor.execute("""
                    SELECT symptom_img FROM appointments WHERE user_id = %s
                """, (user['id'],))
                symptoms = [row['symptom_img'] for row in cursor.fetchall()]

                cursor.execute("""
                    SELECT prescription_filename FROM appointments WHERE user_id = %s
                """, (user['id'],))
                prescriptions = [row['prescription_filename'] for row in cursor.fetchall()]

                user_details.append({
                    "id": user['id'],
                    "name": user['name'],
                    "email": user['email'],
                    "appointments": appointment_count,
                    "symptoms": symptoms,
                    "prescriptions": prescriptions,
                })

        except mysql.connector.Error as err:
            flash(f"Error fetching user data: {err}", "danger")
            return redirect(url_for('admin_dashboard'))
        finally:
            cursor.close()
            connection.close()

        return render_template('admin/view_users.html', users=user_details, query=query)

    flash("No search query provided.", "danger")
    return redirect(url_for('view_users'))





@app.route('/user_details/<int:user_id>', methods=['GET'])
def user_details(user_id):
    print(f"Fetching details for user_id: {user_id}")
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        print(f"User: {user}")

        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('view_users'))

        cursor.execute("SELECT appointment_date, reason FROM appointments WHERE user_id = %s", (user_id,))
        appointments = cursor.fetchall()
        print(f"Appointments: {appointments}")

        return render_template('admin/user_details.html', user=user, appointments=appointments)

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        flash(f"Error fetching user details: {err}", "danger")
        return redirect(url_for('admin_dashboard'))
    finally:
        cursor.close()
        connection.close()

@app.route('/admin/prescription', methods=['GET', 'POST'])
def prescription():
    appointment_id = request.args.get('appointment_id', type=int)

    if request.method == 'POST':
        doctor_name = request.form['doctor_name']
        prescription_date = request.form['date']
        patient_id = request.form['patient_id']
        prescription_details = request.form['prescription']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch patient details
        cursor.execute("SELECT name, age FROM appointments WHERE id = %s", (patient_id,))
        patient = cursor.fetchone()

        if patient:
            # Save the prescription
            cursor.execute("""
                INSERT INTO prescriptions (appointment_id, doctor_name, date, details)
                VALUES (%s, %s, %s, %s)
            """, (patient_id, doctor_name, prescription_date, prescription_details))
            conn.commit()

            # Get the prescription ID
            prescription_id = cursor.lastrowid

            cursor.close()
            conn.close()

            # Redirect to the prescription view
            return redirect(url_for('view_prescription', prescription_id=prescription_id))
        else:
            flash("Patient not found for the given appointment ID.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for('prescription'))

    # Fetch appointments to prefill options in the form
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if appointment_id:
        cursor.execute("SELECT id, name FROM appointments WHERE id = %s AND status = 'approved'", (appointment_id,))
    else:
        cursor.execute("SELECT id, name FROM appointments WHERE status = 'approved'")

    appointments = cursor.fetchall()

    # Remove duplicates based on patient names
    unique_appointments = {}
    for appointment in appointments:
        unique_appointments[appointment['name']] = appointment

    # Convert unique_appointments back to a list
    unique_appointments = list(unique_appointments.values())

    cursor.close()
    conn.close()

    return render_template('admin/prescription.html', appointments=unique_appointments)


@app.route('/admin/view_prescription/<int:prescription_id>', methods=['GET'])
def view_prescription(prescription_id):
    # Fetch prescription details here as shown previously
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch prescription details
    cursor.execute("""
        SELECT p.id AS prescription_id, p.date AS prescription_date, p.details AS prescription_details,
               a.name AS patient_name, a.age, p.doctor_name
        FROM prescriptions p
        JOIN appointments a ON p.appointment_id = a.id
        WHERE p.id = %s
    """, (prescription_id,))
    prescription = cursor.fetchone()

    cursor.close()
    conn.close()

    if not prescription:
        flash("Prescription not found.", "danger")
        return redirect(url_for('manage_appointments'))

    return render_template('admin/prescription_format.html', **prescription)








if __name__ == "__main__":
    app.run( debug=True, host="0.0.0.0", port=5001)
