# collections_os/app.py
# A simple Collections Management System for beginners.

# 1. IMPORT THE MAGIC LIBRARIES
import streamlit as st          # Makes the web interface
import pandas as pd             # Helps us work with tables like Excel
import sqlite3                  # The built-in database (no installation needed)
from datetime import datetime, timedelta  # For calculating dates
import random                   # Just to generate fake IDs for now

# -------------------------------
# 2. SETUP THE DATABASE (SQLite)
# -------------------------------
# This creates a file called 'collections.db' in your folder.
conn = sqlite3.connect('collections.db', check_same_thread=False)
c = conn.cursor()

# Create the 3 tables if they don't exist yet.
c.execute('''CREATE TABLE IF NOT EXISTS customers
             (id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, email TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS loans
             (id INTEGER PRIMARY KEY, 
              customer_id INTEGER, 
              loan_letter TEXT, 
              principal REAL, 
              start_date TEXT, 
              frequency TEXT)''')  # 'Weekly' or 'Monthly'

c.execute('''CREATE TABLE IF NOT EXISTS payments
             (id INTEGER PRIMARY KEY, 
              loan_id INTEGER, 
              amount REAL, 
              payment_date TEXT)''')
conn.commit()

# -------------------------------
# 3. HELPER FUNCTIONS (The Business Logic)
# -------------------------------

# Get the next available loan letter (A, B, C...) for a customer
def get_next_letter(customer_id):
    c.execute("SELECT loan_letter FROM loans WHERE customer_id = ?", (customer_id,))
    used = [row[0] for row in c.fetchall()]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for letter in alphabet:
        if letter not in used:
            return letter
    return "Z"  # Too many loans!

# Calculate Total Due (Principal + 20% interest)
def calculate_total_due(principal):
    return principal * 1.20

# Calculate Next Due Date (Start Date + 7 days or 1 month)
def calculate_next_due(start_date, frequency):
    date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    if frequency == "Weekly":
        return (date_obj + timedelta(days=7)).strftime("%Y-%m-%d")
    else:  # Monthly
        # Add ~30 days for simplicity
        return (date_obj + timedelta(days=30)).strftime("%Y-%m-%d")

# -------------------------------
# 4. THE MAIN STREAMLIT APP INTERFACE
# -------------------------------

st.set_page_config(page_title="Collections OS", layout="wide")
st.title("📊 Collections OS - Loan Manager")

# --- SIDEBAR: Navigation ---
menu = st.sidebar.radio("Navigate", ["➕ New Customer", "💰 New Loan", "💵 Record Payment", "📋 Dashboard"])

# --- PAGE 1: Add Customer ---
if menu == "➕ New Customer":
    st.header("Add a New Customer")
    with st.form("customer_form"):
        name = st.text_input("Full Name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        submitted = st.form_submit_button("Save Customer")
        if submitted and name:
            c.execute("INSERT INTO customers (full_name, phone, email) VALUES (?,?,?)", (name, phone, email))
            conn.commit()
            st.success(f"✅ Customer '{name}' added!")

# --- PAGE 2: Add Loan ---
elif menu == "💰 New Loan":
    st.header("Create a New Loan")
    
    # Dropdown to pick existing customer
    customers_df = pd.read_sql("SELECT id, full_name FROM customers", conn)
    if customers_df.empty:
        st.warning("Please add a customer first.")
    else:
        # 🔥 NEW: Add a search box!
        search_term = st.text_input("🔍 Search for a customer (type their name)", "")
        
        # Filter customers based on search
        if search_term:
            filtered_df = customers_df[customers_df['full_name'].str.contains(search_term, case=False)]
        else:
            filtered_df = customers_df
        
        if filtered_df.empty:
            st.warning(f"No customers found matching '{search_term}'")
        else:
            customer_dict = dict(zip(filtered_df['full_name'], filtered_df['id']))
            selected_customer = st.selectbox("Select Customer", list(customer_dict.keys()))
            customer_id = customer_dict[selected_customer]
            
            # Auto-determine the next Loan Letter
            next_letter = get_next_letter(customer_id)
            st.info(f"📌 Next available Loan Letter: **{next_letter}**")
            
            with st.form("loan_form"):
                principal = st.number_input("Principal Amount ($)", min_value=1.0, step=100.0)
                start_date = st.date_input("Start Date", datetime.today())
                frequency = st.selectbox("Payment Frequency", ["Weekly", "Monthly"])
                
                submitted = st.form_submit_button("Create Loan")
                if submitted and principal > 0:
                    # Calculate values
                    total_due = calculate_total_due(principal)
                    next_due = calculate_next_due(start_date.strftime("%Y-%m-%d"), frequency)
                    
                    # Save to DB
                    c.execute("INSERT INTO loans (customer_id, loan_letter, principal, start_date, frequency) VALUES (?,?,?,?,?)", 
                              (customer_id, next_letter, principal, start_date, frequency))
                    conn.commit()
                    
                    st.success(f"✅ Loan {selected_customer}-Loan{next_letter} created!")
                    st.metric("Total Due (incl. 20% interest)", f"${total_due:,.2f}")
                    st.metric("First Payment Due Date", next_due)

# --- PAGE 3: Record Payment ---
elif menu == "💵 Record Payment":
    st.header("Record a Payment")
    
    loans_df = pd.read_sql("SELECT l.id, c.full_name, l.loan_letter FROM loans l JOIN customers c ON l.customer_id = c.id", conn)
    if loans_df.empty:
        st.warning("No loans exist yet.")
    else:
        # Create a nice label like "John Doe - Loan A"
        loans_df['label'] = loans_df['full_name'] + " - Loan" + loans_df['loan_letter']
        loan_dict = dict(zip(loans_df['label'], loans_df['id']))
        
        selected_loan_label = st.selectbox("Select Loan", list(loan_dict.keys()))
        loan_id = loan_dict[selected_loan_label]
        
        with st.form("payment_form"):
            amount = st.number_input("Amount Paid ($)", min_value=0.01, step=10.0)
            payment_date = st.date_input("Payment Date", datetime.today())
            submitted = st.form_submit_button("Record Payment")
            
            if submitted and amount > 0:
                c.execute("INSERT INTO payments (loan_id, amount, payment_date) VALUES (?,?,?)", 
                          (loan_id, amount, payment_date))
                conn.commit()
                st.success("✅ Payment recorded successfully!")

# --- PAGE 4: The Dashboard ---
elif menu == "📋 Dashboard":
    st.header("Loan Dashboard")
    
    # 1. Get all data with SQL Joins (matching the spec)
    query = """
    SELECT 
        c.full_name as Customer,
        l.loan_letter as Loan,
        l.principal as Principal,
        (l.principal * 1.20) as Total_Due,
        COALESCE(SUM(p.amount), 0) as Total_Paid,
        ((l.principal * 1.20) - COALESCE(SUM(p.amount), 0)) as Remaining_Balance,
        l.start_date as Start_Date,
        l.frequency as Frequency
    FROM loans l
    JOIN customers c ON l.customer_id = c.id
    LEFT JOIN payments p ON l.id = p.loan_id
    GROUP BY l.id
    """
    df = pd.read_sql(query, conn)
    
    if df.empty:
        st.info("No loans to show. Start by adding a customer and a loan!")
    else:
        # Calculate "Days Until Due" (using Start Date + Frequency)
        # This is a simplified dynamic calc for the dashboard
        today = datetime.today().date()
        def calculate_status(row):
            if row['Remaining_Balance'] <= 0:
                return "✅ Paid Off"
            
            # Calculate next due date roughly
            start = datetime.strptime(row['Start_Date'], "%Y-%m-%d").date()
            if row['Frequency'] == "Weekly":
                next_due = start + timedelta(days=7)
            else:
                next_due = start + timedelta(days=30)
            
            days_left = (next_due - today).days
            
            if days_left < 0:
                return "🚨 Overdue"
            elif days_left <= 3:
                return "⚠️ Due Soon"
            else:
                return "🟢 Upcoming"
        
        df['Status'] = df.apply(calculate_status, axis=1)
        
        # Display the table
        st.dataframe(df[['Customer', 'Loan', 'Total_Due', 'Total_Paid', 'Remaining_Balance', 'Status']], use_container_width=True)
        
        # --- WIDGETS (Top Metrics) ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Total Outstanding", f"${df['Remaining_Balance'].sum():,.2f}")
        col2.metric("📌 Overdue Loans", df[df['Status'] == '🚨 Overdue'].shape[0])
        col3.metric("✅ Active Loans", df[df['Status'] != '✅ Paid Off'].shape[0])
        
        # Show customers list too
        st.subheader("Customers")
        customers_df = pd.read_sql("SELECT id, full_name, phone FROM customers", conn)
        st.dataframe(customers_df)

# Close DB connection when app stops (good practice)
# (Streamlit handles this, but we keep it clean)