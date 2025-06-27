# app.py
from flask import Flask, render_template, request, jsonify
import pywhatkit
import time
import os
import threading
import sys
import webbrowser

app = Flask(__name__)

# File to store customer numbers
NUMBERS_FILE = "customer_numbers.txt"

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
    return sorted(list(set(numbers))) # Load unique numbers and sort them

def save_numbers(numbers, filename=NUMBERS_FILE):
    """Saves WhatsApp numbers to a text file."""
    with open(filename, "w") as f:
        for number in sorted(list(set(numbers))): # Save unique and sorted numbers
            f.write(number + "\n")

# --- Background Message Sending Function ---
def _send_messages_in_background(customer_numbers, subject, body):
    """
    Sends WhatsApp messages in a separate thread using pywhatkit.
    This function will interact with the browser.
    """
    full_message = ""
    if subject:
        full_message += f"Subject: {subject}\n\n"
    full_message += body

    if not customer_numbers:
        print("[BACKGROUND SENDER] No customer numbers to send messages to.")
        return

    print(f"[BACKGROUND SENDER] Starting to send messages to {len(customer_numbers)} customers...")
    for i, number in enumerate(customer_numbers):
        print(f"[BACKGROUND SENDER] Sending message to {number} ({i + 1}/{len(customer_numbers)})...")
        try:
            # sendwhatmsg_instantly opens browser and sends message immediately.
            # wait_time: seconds to wait for WhatsApp Web to load
            # tab_close: True to close the tab after sending
            pywhatkit.sendwhatmsg_instantly(number, full_message, wait_time=20, tab_close=True)
            print(f"[BACKGROUND SENDER] Message sent to {number}.")
            time.sleep(5) # Small delay to prevent issues when sending to many numbers quickly
        except Exception as e:
            print(f"[BACKGROUND SENDER ERROR] Failed to send message to {number}: {e}")
            print("[BACKGROUND SENDER ERROR] Please ensure you are logged into WhatsApp Web in your browser and your internet connection is stable.")
    print("[BACKGROUND SENDER] All message sending attempts completed.")


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

        # Basic validation for WhatsApp numbers (starts with +, followed by digits)
        # Allows for spaces and dashes for user input, then cleans it
        cleaned_number = new_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not cleaned_number.startswith('+') or not cleaned_number[1:].isdigit() or len(cleaned_number) < 6:
            return jsonify({'message': 'Invalid number format. Must start with "+" and be followed by digits (e.g., +254712345678).'}), 400

        if cleaned_number in current_numbers:
            return jsonify({'message': f'Number {cleaned_number} already exists.'}), 409 # Conflict

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
        return jsonify({'message': f'Number {number_to_delete} not found.'}), 404
    else:
        return jsonify({'message': f'Number {number_to_delete} deleted successfully!', 'numbers': load_numbers()}), 200

@app.route('/api/send_messages', methods=['POST'])
def send_messages_api():
    """API endpoint to initiate message sending."""
    data = request.json
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    customer_numbers = load_numbers() # Get the latest list of numbers

    if not customer_numbers:
        return jsonify({'message': 'No customer numbers available to send messages to. Please add some first.'}), 400
    if not body:
        return jsonify({'message': 'Message body cannot be empty.'}), 400

    # Start the message sending process in a new background thread
    # This prevents the web request from hanging while messages are being sent
    thread = threading.Thread(target=_send_messages_in_background, args=(customer_numbers, subject, body))
    thread.start()

    return jsonify({'message': 'Message sending initiated in the background. Please monitor your browser for WhatsApp Web activity.'}), 200

# --- Main execution block ---
if __name__ == '__main__':
    # Create the templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)

    # Define the HTML content for index.html
    html_content = """
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
            @apply block w-full rounded-md border-gray-300 shadow-sm p-3 transition duration-150 ease-in-out;
            border-color: rgba(var(--color-primary-red), 0.3); /* Slightly red tint */
        }
        .input-field:focus {
            border-color: rgb(var(--color-success-green)); /* Green focus border */
            box-shadow: 0 0 0 1px rgb(var(--color-success-green)), 0 0 0 3px rgba(var(--color-success-green), 0.2); /* Green ring */
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
            background-color: rgba(var(--color-primary-red), 0.05); /* Very light red background */
        }
        .text-purple-700 { /* Used for Message Composition heading */
            color: rgb(var(--color-success-green-dark)); /* Darker green for Message Composition heading */
        }
        
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-indigo-50 to-purple-50 p-6 flex items-center justify-center">
    <div class="bg-white rounded-xl shadow-2xl p-8 max-w-2xl w-full">
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
            <div id="customer-list-container" class="space-y-3 max-h-60 overflow-y-auto pr-2">
                <!-- Numbers will be loaded here by JavaScript -->
                <p id="no-customers-message" class="text-gray-500 italic">Loading customers...</p>
            </div>
        </div>

        <!-- Message Composition Section -->
        <div class="mb-8 p-6 bg-purple-50 rounded-lg shadow-inner">
            <h2 class="text-2xl font-bold text-purple-700 mb-4">Compose Your Message</h2>
            <div class="mb-4">
                <label for="message-subject" class="block text-sm font-medium text-gray-700 mb-2">
                    Subject (Optional)
                </label>
                <input
                    type="text"
                    id="message-subject"
                    placeholder="e.g., Special Offer for You!"
                    class="input-field"
                />
            </div>
            <div class="mb-6">
                <label for="message-body" class="block text-sm font-medium text-gray-700 mb-2">
                    Message Body <span class="text-red-500">*</span>
                </label>
                <textarea
                    id="message-body"
                    rows="5"
                    placeholder="Type your message here..."
                    class="input-field resize-y"
                ></textarea>
            </div>
            <button onclick="sendMessage()" class="w-full flex items-center justify-center px-6 py-3 btn-primary">
                <svg class="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z" />
                    <path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z" />
                </svg>
                Send Messages to All Customers
            </button>
        </div>
    </div>

    <script>
        const statusMessageDiv = document.getElementById('status-message');
        const customerListContainer = document.getElementById('customer-list-container');
        const customerCountSpan = document.getElementById('customer-count');
        const newNumberInput = document.getElementById('new-number');
        const messageSubjectInput = document.getElementById('message-subject');
        const messageBodyInput = document.getElementById('message-body');
        const noCustomersMessage = document.getElementById('no-customers-message');

        function showStatusMessage(message, type = 'info') {
            statusMessageDiv.textContent = message;
            statusMessageDiv.className = 'mb-6 message-box'; // Reset classes
            statusMessageDiv.classList.add(`message-${type}`);
            statusMessageDiv.classList.remove('hidden');
            // Hide after a few seconds unless it's an error or persistent info
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
                    renderNumbers(data.numbers);
                    showStatusMessage('Customer numbers loaded successfully.', 'success');
                } else {
                    showStatusMessage(`Error loading numbers: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error fetching numbers:', error);
                showStatusMessage('Network error or server unavailable while loading numbers.', 'error');
            }
        }

        function renderNumbers(numbers) {
            customerListContainer.innerHTML = ''; // Clear existing list
            if (numbers.length === 0) {
                customerListContainer.innerHTML = '<p id="no-customers-message" class="text-gray-500 italic">No customers added yet. Add some numbers above!</p>';
                customerCountSpan.textContent = 0;
            } else {
                customerCountSpan.textContent = numbers.length;
                numbers.forEach(number => {
                    const li = document.createElement('li');
                    li.className = 'flex items-center justify-between bg-gray-50 p-3 rounded-lg shadow-sm border border-gray-200';
                    li.innerHTML = `
                        <span class="text-gray-800 font-medium text-lg">${number}</span>
                        <button onclick="deleteNumber('${number}')" class="delete-btn" title="Delete Customer">
                            <svg class="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </button>
                    `;
                    customerListContainer.appendChild(li);
                });
            }
        }

        async function addNumber() {
            const number = newNumberInput.value.trim();
            if (!number) {
                showStatusMessage('Please enter a WhatsApp number.', 'error');
                return;
            }

            // Basic client-side validation
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
                    body: JSON.stringify({ number: cleanedNumber }) // Send the cleaned number
                });
                const data = await response.json();
                if (response.ok) {
                    newNumberInput.value = ''; // Clear input
                    renderNumbers(data.numbers);
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
                    renderNumbers(data.numbers);
                    showStatusMessage(data.message, 'success');
                } else {
                    showStatusMessage(`Error deleting number: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error deleting number:', error);
                showStatusMessage('Network error or server unavailable while deleting number.', 'error');
            }
        }

        async function sendMessage() {
            const subject = messageSubjectInput.value.trim();
            const body = messageBodyInput.value.trim();

            if (!body) {
                showStatusMessage('Message body cannot be empty. Please enter your message.', 'error');
                return;
            }

            // Fetch current numbers before sending to ensure we have the latest list
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

            showStatusMessage('Initiating message sending in the background. Please monitor your browser for WhatsApp Web activity.', 'info');
            try {
                const response = await fetch('/api/send_messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ subject, body })
                });
                const data = await response.json();
                if (response.ok) {
                    // Clear message fields after successful initiation
                    messageSubjectInput.value = '';
                    messageBodyInput.value = '';
                    showStatusMessage(data.message, 'success');
                } else {
                    showStatusMessage(`Error sending messages: ${data.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Error initiating send messages:', error);
                showStatusMessage('Network error or server unavailable while initiating message send.', 'error');
            }
        }

        // Load numbers when the page loads
        document.addEventListener('DOMContentLoaded', fetchNumbers);
    </script>
</body>
</html>
    """

    # Write the HTML content to index.html in the templates directory
    with open(os.path.join('templates', 'index.html'), 'w') as f:
        f.write(html_content)

    # Determine the host and port for the Flask app
    host = '127.0.0.1'
    port = 5000

    print("\n-----------------------------------------------------------")
    print("WhatsApp Message Sender Web UI")
    print("-----------------------------------------------------------")
    print(f"To access the UI, open your web browser and go to:")
    print(f"👉 http://{host}:{port}")
    print("-----------------------------------------------------------")
    print("IMPORTANT:")
    print("1. Ensure you are logged into WhatsApp Web in your default browser.")
    print("2. The script will open new browser tabs/windows to send messages.")
    print("3. Do not close this terminal window while using the UI.")
    print("4. Sending messages will happen in the background, but the browser will be active.")
    print("-----------------------------------------------------------")

    # Open the browser automatically (optional, for convenience)
    try:
        webbrowser.open_new_tab(f"http://{host}:{port}")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        print("Please open the URL manually.")

    # Run the Flask application
    app.run(host=host, port=port, debug=False) # Set debug=True for development, False for production

