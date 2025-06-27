Overview
WhatsApp Message Sender provides a convenient way to manage contacts and send campaign messages in bulk via WhatsApp Web.

Frontend: Modern, responsive UI for easy interaction.
Backend: Python Flask handles logic, contact management, and message automation.
Automation: Uses pywhatkit to automate sending WhatsApp messages.
Note:
This tool automates WhatsApp Web. You must be logged in on your browser for it to work. Use responsibly and be mindful of WhatsApp’s Terms of Service.

✨ Features
📞 Customer Management: Add or delete WhatsApp numbers through the web interface.
🔒 Secure Display: Contact numbers are masked for privacy, with an option to reveal.
📋 Collapsible List: Preview and expand customer contacts.
✍️ Intuitive Composer: Compose messages with subject and body fields.
🚀 Automated Sending: Initiate message sending to all contacts via WhatsApp Web.
📱 Responsive UI: Works beautifully on both desktop and mobile.
🛠️ How It Works
You (Browser Frontend):
Manage contacts and compose messages on the web UI.

Python Flask Server (Backend):
Handles your actions, manages contacts, and orchestrates sending.

WhatsApp Web (Automation):
The backend uses pywhatkit to open WhatsApp Web and send messages automatically.

Workflow Diagram:

[ Your Browser ]
        ⬄
[ Flask Server ]
        ⬄
[ WhatsApp Web ]
You interact with the frontend; the Flask backend processes and automates sending through WhatsApp Web in a browser tab.

🧑‍💻 Setup Guide
1. Prerequisite: Install Python 3
Download and install Python 3.x from python.org.

2. Clone the Repository
git clone https://github.com/RCLDevelopers/WhatsApp-BulkSender.git
cd WhatsApp-BulkSender
3. Install Required Packages
pip install Flask pywhatkit
4. Run the Application
python app.py
Open your browser and go to http://127.0.0.1:5000

🖥️ Live Demo (UI Only)
Interactive demo available in the project web UI. Try adding contacts and composing messages!

⚠️ Disclaimer
This project automates WhatsApp Web for convenience.
Do not use for spam or in violation of WhatsApp’s Terms of Service.
You must be logged into WhatsApp Web in your browser for the automation to work.
🙋‍♂️ Developed By
Rashid
Open for personal and business projects.
Visit Zangtics Digital

📄 License
MIT License. See LICENSE for details.
