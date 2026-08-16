# collections_os/app.py
# Collections Management System with PostgreSQL (Supabase)

import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, timedelta

# -------------------------------
# 1. CONNECT TO SUPABASE (PostgreSQL)
# -------------------------------

# Using direct connection with IPv4 address from pooler
# This bypasses the pooler's tenant identifier requirement
DB_HOST = "44.208.221.186"  # IPv4 address from nslookup
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = "199200@fcbarca"  # Your password from the new Supabase project

def get_connection():
    """Create a connection to Supabase"""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=5432,  # Direct connection port (not pooler)
        sslmode='require'
    )
# Create tables if they don't exist
def init_database():
    conn = get_connection()
    c = conn.cursor()
    
    # Create customers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT
        )
    ''')
    
    # Create loans table
    c.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            loan_letter TEXT,
            principal REAL,
            start_date DATE,
            frequency TEXT
        )
    ''')
    
    # Create payments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
            amount REAL,
            payment_date DATE
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_database()

# -------------------------------
# 2. HELPER FUNCTIONS (Business Logic)
# -------------------------------

def get_next_letter(customer_id):
    """Get the next available loan letter (A, B, C...) for a customer"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT loan_letter FROM loans WHERE customer_id = %s", (customer_id,))
    used = [row[0] for row in c.fetchall()]
    conn.close()
    
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for letter in alphabet:
        if letter not in used:
            return letter
    return "Z"  # Too many loans!

def calculate_total_due(principal):
    """Calculate Total Due (Principal + 20% interest)"""
    return principal * 1.20

def calculate_next_due(start_date, frequency):
    """Calculate Next Due Date (Start Date + 7 days or 1 month)"""
    date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    if frequency == "Weekly":
        return (date_obj + timedelta(days=7)).strftime("%Y-%m-%d")
    else:  # Monthly
        return (date_obj + timedelta(days=30)).strftime("%Y-%m-%d")

# -------------------------------
# 3. MAIN STREAMLIT APP
# -------------------------------

st.set_page_config(page_title="Collections OS", layout="wide")
st.title("📊 Collections OS - Loan Manager")

# --- SIDEBAR: Navigation ---
menu = st.sidebar.radio("Navigate", ["➕ New Customer", "💰 New Loan", "💵 Record Payment", "🗑️ Delete Loan", "📋 Dashboard"])

# --- PAGE 1: Add Customer ---
if menu == "➕ New Customer":
    st.header("Add a New Customer")
    with st.form("customer_form"):
        name = st.text_input("Full Name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        submitted = st.form_submit_button("Save Customer")
        if submitted and name:
            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO customers (full_name, phone, email) VALUES (%s, %s, %s)", (name, phone, email))
            conn.commit()
            conn.close()
            st.success(f"✅ Customer '{name}' added!")

# --- PAGE 2: Add Loan ---
elif menu == "💰 New Loan":
    st.header("Create a New Loan")
    
    conn = get_connection()
    customers_df = pd.read_sql("SELECT id, full_name FROM customers", conn)
    conn.close()
    
    if customers_df.empty:
        st.warning("Please add a customer first.")
    else:
        # Search box for customers
        search_term = st.text_input("🔍 Search for a customer (type their name)", "")
        
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
                    
                    # Save to database
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO loans (customer_id, loan_letter, principal, start_date, frequency) VALUES (%s, %s, %s, %s, %s)",
                        (customer_id, next_letter, principal, start_date, frequency)
                    )
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Loan {selected_customer}-Loan{next_letter} created!")
                    st.metric("Total Due (incl. 20% interest)", f"${total_due:,.2f}")
                    st.metric("First Payment Due Date", next_due)

# --- PAGE 3: Record Payment ---
elif menu == "💵 Record Payment":
    st.header("Record a Payment")
    
    conn = get_connection()
    loans_df = pd.read_sql("""
        SELECT l.id, c.full_name, l.loan_letter 
        FROM loans l 
        JOIN customers c ON l.customer_id = c.id
    """, conn)
    conn.close()
    
    if loans_df.empty:
        st.warning("No loans exist yet.")
    else:
        loans_df['label'] = loans_df['full_name'] + " - Loan" + loans_df['loan_letter']
        loan_dict = dict(zip(loans_df['label'], loans_df['id']))
        
        selected_loan_label = st.selectbox("Select Loan", list(loan_dict.keys()))
        loan_id = loan_dict[selected_loan_label]
        
        with st.form("payment_form"):
            amount = st.number_input("Amount Paid ($)", min_value=0.01, step=10.0)
            payment_date = st.date_input("Payment Date", datetime.today())
            submitted = st.form_submit_button("Record Payment")
            
            if submitted and amount > 0:
                conn = get_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO payments (loan_id, amount, payment_date) VALUES (%s, %s, %s)",
                    (loan_id, amount, payment_date)
                )
                conn.commit()
                conn.close()
                st.success("✅ Payment recorded successfully!")

# --- PAGE 4: Delete Loan ---
elif menu == "🗑️ Delete Loan":
    st.header("🗑️ Delete a Loan")
    st.warning("⚠️ This action cannot be undone! Only delete loans that were created by mistake.")
    
    conn = get_connection()
    loans_df = pd.read_sql("""
        SELECT l.id, c.full_name, l.loan_letter, l.principal 
        FROM loans l 
        JOIN customers c ON l.customer_id = c.id
    """, conn)
    conn.close()
    
    if loans_df.empty:
        st.info("No loans to delete.")
    else:
        loans_df['label'] = loans_df['full_name'] + " - Loan" + loans_df['loan_letter'] + " ($" + loans_df['principal'].astype(str) + ")"
        loan_dict = dict(zip(loans_df['label'], loans_df['id']))
        
        selected_loan = st.selectbox("Select loan to delete", list(loan_dict.keys()))
        loan_id = loan_dict[selected_loan]
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Delete This Loan", type="primary"):
                conn = get_connection()
                c = conn.cursor()
                c.execute("DELETE FROM loans WHERE id = %s", (loan_id,))
                conn.commit()
                conn.close()
                st.success(f"✅ {selected_loan} has been deleted!")
                st.rerun()
        
        with col2:
            if st.button("❌ Cancel"):
                st.info("Deletion cancelled.")

# --- PAGE 5: Dashboard ---
elif menu == "📋 Dashboard":
    st.header("Loan Dashboard")
    
    conn = get_connection()
    
    # Get all data with SQL Joins
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
    GROUP BY l.id, c.full_name, l.loan_letter, l.principal, l.start_date, l.frequency
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    if df.empty:
        st.info("No loans to show. Start by adding a customer and a loan!")
    else:
        # Calculate "Days Until Due" and Status
        today = datetime.today().date()
        def calculate_status(row):
            if row['Remaining_Balance'] <= 0:
                return "✅ Paid Off"
            
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
        
        # Display the table with updated width parameter
        st.dataframe(df[['Customer', 'Loan', 'Total_Due', 'Total_Paid', 'Remaining_Balance', 'Status']], use_container_width=True)
        
        # --- WIDGETS (Top Metrics) ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Total Outstanding", f"${df['Remaining_Balance'].sum():,.2f}")
        col2.metric("📌 Overdue Loans", df[df['Status'] == '🚨 Overdue'].shape[0])
        col3.metric("✅ Active Loans", df[df['Status'] != '✅ Paid Off'].shape[0])
        col4.metric("📊 Total Loans", df.shape[0])
        
        # Show customers list
        st.subheader("Customers")
        conn = get_connection()
        customers_df = pd.read_sql("SELECT id, full_name, phone FROM customers", conn)
        conn.close()
        st.dataframe(customers_df, use_container_width=True)