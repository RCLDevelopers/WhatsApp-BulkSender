# app.py
from flask import Flask, render_template, request, jsonify
import pywhatkit
import time
import os
import threading
import sys
import webbrowser
import uuid
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

app = Flask(__name__)

# File to store customer numbers
NUMBERS_FILE = "customer_numbers.txt"
# File to store scheduled jobs persistently
SCHEDULED_JOBS_FILE = "scheduled_jobs.json"

# Initialize scheduler
scheduler = BackgroundScheduler(daemon=True)

# --- Utility Functions for Number Management ---
def load_numbers(filename=NUMBERS_FILE):
    """Loads WhatsApp numbers from a text file."""
    numbers = []
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                number = line.strip()
                if number:
                    numbers.append(number)
    return sorted(list(set(numbers)))

def save_numbers(numbers, filename=NUMBERS_FILE):
    """Saves WhatsApp numbers to a text file."""
    with open(filename, "w") as f:
        for number in sorted(list(set(numbers))):
            f.write(number + "\n")

# --- Utility Functions for Scheduled Jobs Persistence ---
def load_scheduled_jobs():
    """Loads scheduled jobs from a JSON file."""
    if os.path.exists(SCHEDULED_JOBS_FILE):
        with open(SCHEDULED_JOBS_FILE, "r") as f:
            try:
                jobs_data = json.load(f)
                # Convert string timestamps back to datetime objects
                for job in jobs_data:
                    if 'send_time' in job and isinstance(job['send_time'], str):
                        job['send_time'] = datetime.fromisoformat(job['send_time'])
                return jobs_data
            except json.JSONDecodeError:
                return []
    return []

def save_scheduled_jobs(jobs):
    """Saves scheduled jobs to a JSON file."""
    # Convert datetime objects to ISO format strings for JSON serialization
    jobs_data_to_save = []
    for job in jobs:
        job_copy = job.copy()
        if 'send_time' in job_copy and isinstance(job_copy['send_time'], datetime):
            job_copy['send_time'] = job_copy['send_time'].isoformat()
        jobs_data_to_save.append(job_copy)
    
    with open(SCHEDULED_JOBS_FILE, "w") as f:
        json.dump(jobs_data_to_save, f, indent=4)

def add_job_to_persistence(job_data):
    """Adds a new job to the persistent storage."""
    jobs = load_scheduled_jobs()
    jobs.append(job_data)
    save_scheduled_jobs(jobs)

def remove_job_from_persistence(job_id):
    """Removes a job from the persistent storage."""
    jobs = load_scheduled_jobs()
    jobs = [job for job in jobs if job['id'] != job_id]
    save_scheduled_jobs(jobs)

def update_job_status_in_persistence(job_id, status):
    """Updates the status of a job in persistent storage."""
    jobs = load_scheduled_jobs()
    for job in jobs:
        if job['id'] == job_id:
            job['status'] = status
            break
    save_scheduled_jobs(jobs)

# --- Message Sending Job Function (Called by Scheduler) ---
def send_whatsapp_job(job_id, phone_number, subject, body):
    """
    Function executed by APScheduler to send a WhatsApp message.
    Updates the job status in persistent storage after attempting to send.
    """
    full_message = ""
    if subject:
        full_message += f"Subject: {subject}\n\n"
    full_message += body

    print(f"[SCHEDULED SENDER] Attempting to send message (Job ID: {job_id}) to {phone_number}...")
    try:
        # pywhatkit.sendwhatmsg_instantly directly opens browser without waiting for specific time within minute
        pywhatkit.sendwhatmsg_instantly(phone_number, full_message, wait_time=20, tab_close=True)
        print(f"[SCHEDULED SENDER] Message (Job ID: {job_id}) sent successfully to {phone_number}.")
        update_job_status_in_persistence(job_id, 'sent')
    except Exception as e:
        print(f"[SCHEDULED SENDER ERROR] Failed to send message (Job ID: {job_id}) to {phone_number}: {e}")
        print("[SCHEDULED SENDER ERROR] Please ensure WhatsApp Web is logged in.")
        update_job_status_in_persistence(job_id, f'failed: {str(e)}')
    finally:
        # Optionally, remove job from scheduler's active jobs after completion/failure
        # If the job is one-off ('date' trigger), APScheduler automatically removes it after execution.
        pass

# --- Flask Routes ---
@app.route('/')
def index():
    """Renders the main HTML page for the UI."""
    return render_template('index.html')

@app.route('/api/numbers', methods=['GET', 'POST'])
def handle_numbers():
    """API endpoint for managing customer numbers (GET and POST)."""
    current_numbers = load_numbers()

    if request.method == 'GET':
        return jsonify({'numbers': current_numbers})
    elif request.method == 'POST':
        data = request.json
        new_number = data.get('number', '').strip()

        if not new_number:
            return jsonify({'message': 'Number cannot be empty.'}), 400

        cleaned_number = new_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not cleaned_number.startswith('+') or not cleaned_number[1:].isdigit() or len(cleaned_number) < 6:
            return jsonify({'message': 'Invalid number format. Must start with "+" and be followed by digits (e.g., +254712345678).'}), 400

        if cleaned_number in current_numbers:
            return jsonify({'message': f'Number {cleaned_number} already exists.'}), 409

        current_numbers.append(cleaned_number)
        save_numbers(current_numbers)
        return jsonify({'message': f'Number {cleaned_number} added successfully!', 'numbers': load_numbers()}), 201

@app.route('/api/numbers/<string:number_to_delete>', methods=['DELETE'])
def delete_number(number_to_delete):
    """API endpoint for deleting a customer number."""
    current_numbers = load_numbers()
    if number_to_delete in current_numbers:
        current_numbers.remove(number_to_delete)
        save_numbers(current_numbers)
        return jsonify({'message': f'Number {number_to_delete} deleted successfully!', 'numbers': load_numbers()}), 200
    else:
        return jsonify({'message': f'Number {number_to_delete} not found.'}), 404

@app.route('/api/schedule_message', methods=['POST'])
def schedule_message_api():
    """API endpoint to schedule a message or send immediately."""
    data = request.json
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    scheduled_date_str = data.get('scheduled_date', '').strip()
    scheduled_time_str = data.get('scheduled_time', '').strip()
    
    customer_numbers = load_numbers()

    if not customer_numbers:
        return jsonify({'message': 'No customer numbers available to send messages to. Please add some first.'}), 400
    if not subject:
        return jsonify({'message': 'Message subject cannot be empty.'}), 400
    if not body:
        return jsonify({'message': 'Message body cannot be empty.'}), 400

    if scheduled_date_str and scheduled_time_str:
        # Schedule for future
        try:
            combined_datetime_str = f"{scheduled_date_str} {scheduled_time_str}"
            scheduled_datetime = datetime.fromisoformat(combined_datetime_str)

            # Ensure the scheduled time is in the future
            if scheduled_datetime <= datetime.now():
                return jsonify({'message': 'Scheduled time must be in the future.'}), 400

            for number in customer_numbers:
                job_id = str(uuid.uuid4())
                scheduler.add_job(
                    send_whatsapp_job, 
                    trigger=DateTrigger(run_date=scheduled_datetime),
                    args=[job_id, number, subject, body], 
                    id=job_id,
                    misfire_grace_time=60 # seconds
                )
                add_job_to_persistence({
                    'id': job_id,
                    'number': number,
                    'subject': subject,
                    'body': body,
                    'send_time': scheduled_datetime,
                    'status': 'pending'
                })
            return jsonify({'message': 'Messages scheduled successfully!', 'type': 'scheduled'}), 200
        except ValueError as e:
            return jsonify({'message': f'Invalid date or time format: {e}'}), 400
        except Exception as e:
            return jsonify({'message': f'Failed to schedule messages: {e}'}), 500
    else:
        # Send immediately
        # Use a new thread for immediate sending to avoid blocking the API response
        send_thread = threading.Thread(target=_send_messages_immediately, args=(customer_numbers, subject, body))
        send_thread.start()
        return jsonify({'message': 'Immediate message sending initiated. Please monitor your browser.', 'type': 'immediate'}), 200

def _send_messages_immediately(customer_numbers, subject, body):
    """Helper function to send messages immediately in a separate thread."""
    full_message = ""
    if subject:
        full_message += f"Subject: {subject}\n\n"
    full_message += body
    
    for number in customer_numbers:
        try:
            pywhatkit.sendwhatmsg_instantly(number, full_message, wait_time=20, tab_close=True)
            print(f"[IMMEDIATE SENDER] Message sent to {number}.")
            time.sleep(5) # Small delay between messages
        except Exception as e:
            print(f"[IMMEDIATE SENDER ERROR] Failed to send message to {number}: {e}")

@app.route('/api/scheduled_messages', methods=['GET'])
def get_scheduled_messages_api():
    """API endpoint to get list of scheduled messages."""
    jobs = load_scheduled_jobs()
    # Filter for pending and convert datetime to string for JSON serialization
    pending_jobs = []
    for job in jobs:
        if job.get('status') == 'pending':
            job_copy = job.copy()
            if isinstance(job_copy['send_time'], datetime):
                job_copy['send_time'] = job_copy['send_time'].isoformat()
            pending_jobs.append(job_copy)
    return jsonify({'scheduled_messages': pending_jobs}), 200

@app.route('/api/scheduled_messages/<string:job_id>', methods=['DELETE'])
def cancel_scheduled_message_api(job_id):
    """API endpoint to cancel a specific scheduled message."""
    try:
        scheduler.remove_job(job_id)
        remove_job_from_persistence(job_id)
        return jsonify({'message': f'Scheduled message {job_id} cancelled successfully.'}), 200
    except Exception as e:
        return jsonify({'message': f'Failed to cancel job {job_id}: {e}'}), 404

# --- Startup Logic ---
def setup_scheduler():
    """Loads pending jobs from persistence and re-adds them to the scheduler."""
    jobs = load_scheduled_jobs()
    for job_data in jobs:
        if job_data.get('status') == 'pending':
            try:
                # Ensure send_time is datetime object
                if isinstance(job_data['send_time'], str):
                    job_data['send_time'] = datetime.fromisoformat(job_data['send_time'])

                scheduler.add_job(
                    send_whatsapp_job, 
                    trigger=DateTrigger(run_date=job_data['send_time']),
                    args=[job_data['id'], job_data['number'], job_data['subject'], job_data['body']], 
                    id=job_data['id'],
                    misfire_grace_time=60 # seconds
                )
                print(f"Re-added scheduled job {job_data['id']} for {job_data['send_time']}")
            except Exception as e:
                print(f"Error re-adding job {job_data['id']}: {e}. Skipping.")
                # Mark as failed if cannot re-add (e.g., time passed while server was down)
                update_job_status_in_persistence(job_data['id'], f'failed: re-add error ({str(e)})')


# --- Main execution block ---
if __name__ == '__main__':
    # Create the templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)

    # Define the HTML content for index.html (updated below)
    html_content = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Campaign Sender</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --color-primary-red: 210, 1, 0;
            --color-primary-red-light: 255, 100, 100; /* Lighter for backgrounds */
            --color-primary-red-dark: 150, 0, 0; /* Darker for hover */

            --color-success-green: 6, 140, 17;
            --color-success-green-light: 200, 240, 200; /* Lighter for backgrounds */
            --color-success-green-dark: 0, 100, 0; /* Darker for text/border */

            --color-info-orange: 255, 159, 3;
            --color-info-orange-light: 255, 220, 180; /* Lighter for backgrounds */
            --color-info-orange-dark: 200, 120, 0; /* Darker for text/border */
        }

        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(to bottom right, rgb(var(--color-primary-red-light)) 5%, rgb(var(--color-info-orange-light)) 95%);
        }
        .btn-primary {
            background-color: rgb(var(--color-primary-red));
            color: white;
            border-radius: 0.375rem; /* rounded-md */
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); /* shadow-lg */
            transition-property: all;
            transition-duration: 150ms;
            transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); /* ease-in-out */
        }
        .btn-primary:hover {
            background-color: rgb(var(--color-primary-red-dark));
        }
        .btn-primary:focus {
            outline: none;
            box-shadow: 0 0 0 2px rgb(255, 255, 255), 0 0 0 4px rgba(var(--color-primary-red), 0.5); /* focus:ring-offset-2 focus:ring-indigo-500 */
        }
        .btn-secondary {
            @apply bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition duration-150 ease-in-out shadow-sm;
        }
        .input-field {
            @apply block w-full rounded-md border-gray-300 shadow-sm p-4 transition duration-150 ease-in-out; /* Changed p-3 to p-4 */
            border-color: rgba(var(--color-primary-red), 0.3); /* Slightly red tint */
        }
        .input-field:focus {
            border-color: rgb(var(--color-success-green)); /* Green focus border */
            box-shadow: 0 0 0 1px rgb(var(--color-success-green)), 0 0 0 3px rgba(var(--color-success-green), 0.2); /* Green ring */
        }
        .input-field::placeholder { /* Added specific placeholder styling */
            color: #6b7280; /* Tailwind gray-500 equivalent for better visibility */
            opacity: 1; /* Ensures consistency across browsers */
        }
        .delete-btn {
            color: rgb(var(--color-primary-red));
            transition-property: all;
            transition-duration: 150ms;
            transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); /* ease-in-out */
            padding: 0.25rem; /* p-1 */
            border-radius: 9999px; /* rounded-full */
        }
        .delete-btn:hover {
            color: rgb(var(--color-primary-red-dark));
            background-color: rgba(var(--color-primary-red), 0.05); /* light red hover background */
        }
        .view-contact-btn {
            @apply ml-2 px-2 py-1 bg-gray-300 text-gray-800 rounded-md text-xs hover:bg-gray-400 transition duration-150 ease-in-out;
        }

        .message-box {
            @apply p-4 rounded-lg text-sm;
        }
        .message-success {
            background-color: rgba(var(--color-success-green), 0.1);
            color: rgb(var(--color-success-green-dark));
            border: 1px solid rgba(var(--color-success-green), 0.3);
        }
        .message-error {
            background-color: rgba(var(--color-primary-red), 0.1);
            color: rgb(var(--color-primary-red-dark));
            border: 1px solid rgba(var(--color-primary-red), 0.3);
        }
        .message-info {
            background-color: rgba(var(--color-info-orange), 0.1);
            color: rgb(var(--color-info-orange-dark));
            border: 1px solid rgba(var(--color-info-orange), 0.3);
        }

        /* Adjust sections backgrounds and headings */
        .bg-indigo-50 { /* Used for Add Number Section */
            background-color: rgba(var(--color-info-orange), 0.1); /* Light orange background */
        }
        .text-indigo-800 { /* Used for main heading */
            color: rgb(var(--color-primary-red-dark)); /* Darker red for main heading */
        }
        .text-indigo-700 { /* Used for section headings */
            color: rgb(var(--color-primary-red-dark)); /* Darker red for section headings */
        }

        .bg-purple-50 { /* Used for Message Composition Section */
            background-color: rgba(var(--color-primary-red-light), 0.3); /* Stronger pink background for compose section */
        }
        .text-purple-700 { /* Used for Message Composition heading */
            color: rgb(var(--color-success-green-dark)); /* Darker green for Message Composition heading */
        }
        
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-indigo-50 to-purple-50 p-6 flex items-center justify-center">
    <div class="bg-white rounded-xl shadow-2xl p-8 max-w-3xl w-full"> <!-- max-w-3xl for wider layout -->
        <h1 class="text-4xl font-extrabold text-center text-indigo-800 mb-8 tracking-tight">
            WhatsApp Message Sender
        </h1>

        <!-- Message/Status Box -->
        <div id="status-message" class="hidden mb-6 message-box"></div>

        <!-- Add New Number Section -->
        <div class="mb-8 p-6 bg-indigo-50 rounded-lg shadow-inner">
            <h2 class="text-2xl font-bold text-indigo-700 mb-4">Add Customer Number</h2>
            <div class="mb-4">
                <label for="new-number" class="block text-sm font-medium text-gray-700 mb-2">
                    WhatsApp Number (e.g., +254712345678)
                </label>
                <div class="flex space-x-3">
                    <input
                        type="text"
                        id="new-number"
                        placeholder="Enter number with country code"
                        class="flex-1 input-field"
                    />
                    <button onclick="addNumber()" class="px-5 py-2 btn-primary">
                        Add
                    </button>
                </div>
            </div>
        </div>

        <!-- Customer List Section -->
        <div class="mb-8">
            <h2 class="text-2xl font-bold text-indigo-700 mb-4">Your Customer List (<span id="customer-count">0</span>)</h2>
            <div id="customer-list-container" class="space-y-3 max-h-60 overflow-y-auto pr-2 border border-gray-200 rounded-lg p-2">
                <!-- Numbers will be loaded here by JavaScript -->
                <p id="no-customers-message" class="text-gray-500 italic">Loading customers...</p>
            </div>
            <button id="toggle-view-btn" onclick="toggleViewAllContacts()" class="mt-4 w-full flex items-center justify-center px-4 py-2 btn-secondary hidden">
                View All Contacts
            </button>
        </div>

        <!-- Message Composition Section -->
        <div class="mb-8 p-6 bg-purple-50 rounded-lg shadow-inner">
            <h2 class="text-2xl font-bold text-purple-700 mb-4">Compose Your Message</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                    <label for="scheduled-date" class="block text-sm font-medium text-gray-700 mb-2">
                        Schedule Date (Optional)
                    </label>
                    <input
                        type="date"
                        id="scheduled-date"
                        class="input-field"
                    />
                </div>
                <div>
                    <label for="scheduled-time" class="block text-sm font-medium text-gray-700 mb-2">
                        Schedule Time (Optional)
                    </label>
                    <input
                        type="time"
                        id="scheduled-time"
                        class="input-field"
                    />
                </div>
            </div>
            <div class="mb-4">
                <label for="message-subject" class="block text-sm font-medium text-gray-700 mb-2">
                    Subject <span class="text-red-500">*</span>
                </label>
                <input
                    type="text"
                    id="message-subject"
                    placeholder="e.g., Special Offer for You!"
                    class="input-field"
                    required
                />
            </div>
            <div class="mb-6">
                <label for="message-body" class="block text-sm font-medium text-gray-700 mb-2">
                    Message Body <span class="text-red-500">*</span>
                </label>
                <textarea
                    id="message-body"
                    rows="8" 
                    placeholder="Type your message here..."
                    class="input-field resize-y"
                    required
                ></textarea>
            </div>
            <button onclick="scheduleOrSendMessage()" class="w-full flex items-center justify-center px-6 py-3 btn-primary">
                <svg class="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z" />
                    <path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z" />
                </svg>
                Schedule Message / Send Now
            </button>
        </div>

        <!-- Scheduled Messages Section -->
        <div class="mb-8 p-6 bg-gray-50 rounded-lg shadow-inner">
            <h2 class="text-2xl font-bold text-indigo-700 mb-4">Scheduled Messages (<span id="scheduled-count">0</span>)</h2>
            <div id="scheduled-messages-container" class="space-y-3 max-h-60 overflow-y-auto pr-2 border border-gray-200 rounded-lg p-2">
                <p id="no-scheduled-messages-message" class="text-gray-500 italic">No messages scheduled.</p>
            </div>
        </div>

    </div>

    <script>
        const statusMessageDiv = document.getElementById('status-message');
        const customerListContainer = document.getElementById('customer-list-container');
        const customerCountSpan = document.getElementById('customer-count');
        const newNumberInput = document.getElementById('new-number');
        const messageSubjectInput = document.getElementById('message-subject');
        const messageBodyInput = document.getElementById('message-body');
        const scheduledDateInput = document.getElementById('scheduled-date');
        const scheduledTimeInput = document.getElementById('scheduled-time');
        const noCustomersMessage = document.getElementById('no-customers-message');
        const toggleViewBtn = document.getElementById('toggle-view-btn');
        const scheduledMessagesContainer = document.getElementById('scheduled-messages-container');
        const scheduledCountSpan = document.getElementById('scheduled-count');
        const noScheduledMessagesMessage = document.getElementById('no-scheduled-messages-message');

        let allCustomers = [];
        const initialDisplayLimit = 2;
        let isViewingAll = false;

        function showStatusMessage(message, type = 'info') {
            statusMessageDiv.textContent = message;
            statusMessageDiv.className = 'mb-6 message-box';
            statusMessageDiv.classList.add(`message-${type}`);
            statusMessageDiv.classList.remove('hidden');
            if (type !== 'error') {
                setTimeout(() => {
                    statusMessageDiv.classList.add('hidden');
                }, 5000);
            }
        }

        async function fetchNumbers() {
            showStatusMessage('Loading customer numbers...');
            try {
                const response = await fetch('/api/numbers');
                const data = await response.json();
                if (response.ok) {
                    allCustomers = data.numbers;
                    renderNumbers();
                    showStatusMessage('Customer numbers loaded successfully.', 'success');
                } else {
                    showStatusMessage(`Error loading numbers: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error fetching numbers:', error);
                showStatusMessage('Network error or server unavailable while loading numbers.', 'error');
            }
        }

        function maskNumber(number) {
            if (number.length <= 6) return number;
            const prefix = number.substring(0, 5);
            const suffix = number.substring(number.length - 2);
            return `${prefix}*****${suffix}`;
        }

        function renderNumbers() {
            customerListContainer.innerHTML = '';
            customerCountSpan.textContent = allCustomers.length;

            if (allCustomers.length === 0) {
                customerListContainer.innerHTML = '<p id="no-customers-message" class="text-gray-500 italic">No customers added yet. Add some numbers above!</p>';
                toggleViewBtn.classList.add('hidden');
                return;
            }

            const numbersToDisplay = isViewingAll ? allCustomers : allCustomers.slice(0, initialDisplayLimit);

            numbersToDisplay.forEach(number => {
                const li = document.createElement('li');
                li.className = 'flex items-center justify-between bg-gray-50 p-3 rounded-lg shadow-sm border border-gray-200';
                li.setAttribute('data-full-number', number);
                li.setAttribute('data-masked', 'true');

                const maskedNum = maskNumber(number);

                li.innerHTML = `
                    <span class="text-gray-800 font-medium text-lg" id="display-number-${number}">${maskedNum}</span>
                    <div class="flex items-center space-x-2">
                        <button onclick="toggleNumberVisibility(this, '${number}')" class="view-contact-btn">
                            View Contact
                        </button>
                        <button onclick="deleteNumber('${number}')" class="delete-btn" title="Delete Customer">
                            <svg class="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </button>
                    </div>
                `;
                customerListContainer.appendChild(li);
            });

            if (allCustomers.length > initialDisplayLimit) {
                toggleViewBtn.classList.remove('hidden');
                toggleViewBtn.textContent = isViewingAll ? 'View Fewer Contacts' : 'View All Contacts';
            } else {
                toggleViewBtn.classList.add('hidden');
            }
        }

        function toggleViewAllContacts() {
            isViewingAll = !isViewingAll;
            renderNumbers();
        }

        function toggleNumberVisibility(buttonElement, fullNumber) {
            const listItem = buttonElement.closest('li');
            const displaySpan = listItem.querySelector('span');
            const isMasked = listItem.getAttribute('data-masked') === 'true';

            if (isMasked) {
                displaySpan.textContent = fullNumber;
                listItem.setAttribute('data-masked', 'false');
                buttonElement.textContent = 'Hide Contact';
            } else {
                displaySpan.textContent = maskNumber(fullNumber);
                listItem.setAttribute('data-masked', 'true');
                buttonElement.textContent = 'View Contact';
            }
        }

        async function addNumber() {
            const number = newNumberInput.value.trim();
            if (!number) {
                showStatusMessage('Please enter a WhatsApp number.', 'error');
                return;
            }

            const cleanedNumber = number.replace(/[\s-()]/g, '');
            if (!cleanedNumber.startsWith('+') || cleanedNumber.length < 6 || !cleanedNumber.substring(1).match(/^\d+$/)) {
                showStatusMessage('Invalid number format. Must start with "+" and be followed by digits (e.g., +254712345678).', 'error');
                return;
            }

            showStatusMessage('Adding number...', 'info');
            try {
                const response = await fetch('/api/numbers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ number: cleanedNumber })
                });
                const data = await response.json();
                if (response.ok) {
                    newNumberInput.value = '';
                    allCustomers = data.numbers;
                    renderNumbers();
                    showStatusMessage(data.message, 'success');
                } else {
                    showStatusMessage(`Error adding number: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error adding number:', error);
                showStatusMessage('Network error or server unavailable while adding number.', 'error');
            }
        }

        async function deleteNumber(number) {
            if (!confirm(`Are you sure you want to delete ${number}?`)) {
                return;
            }
            showStatusMessage(`Deleting ${number}...`, 'info');
            try {
                const response = await fetch(`/api/numbers/${encodeURIComponent(number)}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                if (response.ok) {
                    allCustomers = data.numbers;
                    renderNumbers();
                    showStatusMessage(data.message, 'success');
                } else {
                    showStatusMessage(`Error deleting number: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error deleting number:', error);
                showStatusMessage('Network error or server unavailable while deleting number.', 'error');
            }
        }

        async function scheduleOrSendMessage() {
            const subject = messageSubjectInput.value.trim();
            const body = messageBodyInput.value.trim();
            const scheduledDate = scheduledDateInput.value;
            const scheduledTime = scheduledTimeInput.value;

            if (!subject) {
                showStatusMessage('Message subject cannot be empty. Please enter a subject.', 'error');
                return;
            }
            if (!body) {
                showStatusMessage('Message body cannot be empty. Please enter your message.', 'error');
                return;
            }

            let currentNumbers = [];
            try {
                const response = await fetch('/api/numbers');
                const data = await response.json();
                if (response.ok) {
                    currentNumbers = data.numbers;
                } else {
                    showStatusMessage(`Failed to get customer list before sending: ${data.message || 'Unknown error'}`, 'error');
                    return;
                }
            } catch (error) {
                console.error('Error fetching numbers before sending:', error);
                showStatusMessage('Network error while getting customer list before sending.', 'error');
                return;
            }

            if (currentNumbers.length === 0) {
                showStatusMessage('No customer numbers added yet. Cannot send messages.', 'error');
                return;
            }

            const payload = {
                subject: subject,
                body: body,
                scheduled_date: scheduledDate,
                scheduled_time: scheduledTime
            };

            showStatusMessage('Processing message...', 'info');
            try {
                const response = await fetch('/api/schedule_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (response.ok) {
                    messageSubjectInput.value = '';
                    messageBodyInput.value = '';
                    scheduledDateInput.value = '';
                    scheduledTimeInput.value = '';
                    showStatusMessage(data.message, 'success');
                    fetchScheduledMessages(); // Refresh scheduled messages list
                } else {
                    showStatusMessage(`Error: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error scheduling/sending messages:', error);
                showStatusMessage('Network error or server unavailable. Check console for details.', 'error');
            }
        }

        async function fetchScheduledMessages() {
            showStatusMessage('Loading scheduled messages...', 'info');
            try {
                const response = await fetch('/api/scheduled_messages');
                const data = await response.json();
                if (response.ok) {
                    renderScheduledMessages(data.scheduled_messages);
                    showStatusMessage('Scheduled messages loaded.', 'success');
                } else {
                    showStatusMessage(`Error loading scheduled messages: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error fetching scheduled messages:', error);
                showStatusMessage('Network error or server unavailable while loading scheduled messages.', 'error');
            }
        }

        function renderScheduledMessages(messages) {
            scheduledMessagesContainer.innerHTML = '';
            scheduledCountSpan.textContent = messages.length;

            if (messages.length === 0) {
                scheduledMessagesContainer.innerHTML = '<p id="no-scheduled-messages-message" class="text-gray-500 italic">No messages scheduled.</p>';
                return;
            }

            messages.forEach(job => {
                const li = document.createElement('li');
                li.className = 'flex flex-col md:flex-row items-start md:items-center justify-between bg-white p-3 rounded-lg shadow-sm border border-gray-200';
                
                const sendTime = new Date(job.send_time);
                const formattedTime = sendTime.toLocaleString(); // Format date and time for display

                li.innerHTML = `
                    <div class="flex-grow">
                        <p class="font-bold text-gray-800">To: ${maskNumber(job.number)}</p>
                        <p class="text-sm text-gray-700">Subject: ${job.subject}</p>
                        <p class="text-xs text-gray-500">Scheduled: ${formattedTime}</p>
                    </div>
                    <div class="mt-2 md:mt-0 md:ml-4 flex-shrink-0">
                        <button onclick="cancelScheduledMessage('${job.id}')" class="px-3 py-1 text-red-600 bg-red-100 rounded-md hover:bg-red-200 text-sm">
                            Cancel
                        </button>
                    </div>
                `;
                scheduledMessagesContainer.appendChild(li);
            });
        }

        async function cancelScheduledMessage(jobId) {
            if (!confirm('Are you sure you want to cancel this scheduled message?')) {
                return;
            }
            showStatusMessage(`Cancelling message (ID: ${jobId})...`, 'info');
            try {
                const response = await fetch(`/api/scheduled_messages/${jobId}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                if (response.ok) {
                    showStatusMessage(data.message, 'success');
                    fetchScheduledMessages(); // Refresh list after cancellation
                } else {
                    showStatusMessage(`Error cancelling message: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error cancelling message:', error);
                showStatusMessage('Network error or server unavailable while cancelling message.', 'error');
            }
        }


        // Load numbers and scheduled messages when the page loads
        document.addEventListener('DOMContentLoaded', () => {
            fetchNumbers();
            fetchScheduledMessages();
        });
    </script>
</body>
</html>
"""

    # Write the HTML content to index.html in the templates directory
    with open(os.path.join('templates', 'index.html'), 'w') as f:
        f.write(html_content)

    # Ensure scheduled_jobs.json exists
    if not os.path.exists(SCHEDULED_JOBS_FILE):
        with open(SCHEDULED_JOBS_FILE, 'w') as f:
            json.dump([], f)

    # Setup and start scheduler
    setup_scheduler()
    scheduler.start()

    # Add a shutdown hook for the scheduler
    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))

    # Determine the host and port for the Flask app
    host = '127.0.0.1'
    port = 5000

    print("\n-----------------------------------------------------------")
    print("WhatsApp Message Sender Web UI with Scheduler")
    print("-----------------------------------------------------------")
    print(f"To access the UI, open your web browser and go to:")
    print(f"👉 http://{host}:{port}")
    print("-----------------------------------------------------------")
    print("IMPORTANT:")
    print("1. Ensure you are logged into WhatsApp Web in your default browser.")
    print("2. The script will open new browser tabs/windows to send messages.")
    print("3. This terminal window MUST remain open for scheduled messages to be sent.")
    print("4. Scheduled messages are processed by a background scheduler.")
    print("-----------------------------------------------------------")

    # Open the browser automatically (optional, for convenience)
    try:
        webbrowser.open_new_tab(f"http://{host}:{port}")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        print("Please open the URL manually.")

    # Run the Flask application
    app.run(host=host, port=port, debug=False, use_reloader=False) # use_reloader=False is crucial for APScheduler
