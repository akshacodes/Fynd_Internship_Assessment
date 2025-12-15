import streamlit as st
import pandas as pd
import google.generativeai as genai
import time
import os
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- AUTHENTICATION & CONNECTION (Google Sheets) ---

@st.cache_resource
def get_google_sheet():
    try:
        # Define the scope for Sheets and Drive APIs
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # Load credentials from Streamlit secrets
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
        # Authorize and open the sheet
        client = gspread.authorize(creds)
        # Opening the specific sheet name
        sheet = client.open("Fynd Review Dashboard").sheet1  
        return sheet
    except Exception as e:
        return None

# --- AUTHENTICATION (Gemini AI) ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    # Fallback for local testing
    if "GOOGLE_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

def get_gemini_response(prompt):
    try:
        # Using the stable model to avoid 429 errors
        model = genai.GenerativeModel("models/gemini-flash-latest")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- DATA HANDLING ---

def load_data():
    """Fetches all data from the Google Sheet."""
    sheet = get_google_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            # Force all column names to be lowercase to fix "Anonymous" and empty text issues
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            return pd.DataFrame()
    return pd.DataFrame()

def save_entry(rating, text, reply, summary, action):
    """Appends a new review row to the Google Sheet."""
    sheet = get_google_sheet()
    if not sheet:
        st.error("Database connection failed. Cannot save.")
        return

    fake_names = ["Alex R.", "Sam K.", "Jordan P.", "Casey M.", "Taylor S.", "Priya D.", "Rohan G."]
    fake_avatars = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🐯"]
    
    # Prepare the row data (Order matches Sheet Headers)
    new_row = [
        datetime.now().strftime("%Y-%m-%d"), # timestamp
        rating,                              # rating
        text,                                # review_text
        reply,                               # ai_reply
        summary,                             # ai_summary
        action,                              # ai_action
        random.choice(fake_names),           # user_name
        random.choice(fake_avatars)          # avatar
    ]
    
    try:
        sheet.append_row(new_row)
    except Exception as e:
        st.error(f"Failed to save data: {e}")

# --- AI GENERATION ---
def generate_ai_content(review_text, rating):
    # 1. User Reply
    reply_prompt = f"""
    You are a business owner replying to a customer review. 
    Review: "{review_text}" (Rating: {rating}/5).
    Write a short, professional, and grateful response. Max 2 sentences.
    """
    reply = get_gemini_response(reply_prompt)

    # 2. Admin Summary & Action
    admin_prompt = f"""
    Analyze this review: "{review_text}" (Rating: {rating}/5).
    1. Summarize key point in 5 words.
    2. Suggest one specific business action.
    
    Format:
    Summary: <text>
    Action: <text>
    """
    analysis = get_gemini_response(admin_prompt)
    
    try:
        lines = analysis.split('\n')
        summary = next((line.split(': ')[1] for line in lines if 'Summary:' in line), "General Feedback")
        action = next((line.split(': ')[1] for line in lines if 'Action:' in line), "Review Manually")
    except:
        summary = "Analysis Pending"
        action = "Review Manually"

    return reply, summary, action

# --- MAIN APP UI ---
st.set_page_config(page_title="Fynd Reviews", layout="wide")

st.title("🚀 Fynd Dashboard")

tab_user, tab_admin = st.tabs(["⭐ Public Reviews", "🛡️ Admin Dashboard"])

# === DASHBOARD 1: USER VIEW ===
with tab_user:
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("Rate your experience")
        with st.form("user_form"):
            st.write("Click to rate:")
            # Use st.feedback (Newer Streamlit versions) or slider if preferred
            rating_input = st.feedback("stars")
            stars = (rating_input + 1) if rating_input is not None else 5
            
            review = st.text_area("Share details of your own experience")
            submitted = st.form_submit_button("Post Review")
            
            if submitted and review:
                with st.spinner("Posting..."):
                    reply, summary, action = generate_ai_content(review, stars)
                    save_entry(stars, review, reply, summary, action)
                    st.success("Thanks for sharing!")
                    time.sleep(1)
                    st.rerun()

    with col_right:
        data = load_data()
        if not data.empty:
            # Filter out error rows for users
            if 'ai_reply' in data.columns:
                clean_data = data[~data['ai_reply'].astype(str).str.contains("Error|429|404", case=False, na=False)]
            else:
                clean_data = data
            
            if not clean_data.empty:
                if 'rating' in clean_data.columns:
                    avg_rating = clean_data['rating'].mean()
                    st.markdown(f"### {avg_rating:.1f} ⭐⭐⭐⭐⭐ ({len(clean_data)} reviews)")
                st.divider()
                
                # Robust Display Loop
                for index, row in clean_data.sort_index(ascending=False).iterrows():
                    c1, c2 = st.columns([1, 10])
                    
                    # Use .get() to avoid crashing if columns are missing
                    avatar = row.get('avatar', '👤')
                    name = row.get('user_name', 'Anonymous')
                    timestamp = row.get('timestamp', '')
                    rating_val = int(row.get('rating', 5))
                    text_val = row.get('review_text', '')
                    reply_val = str(row.get('ai_reply', '')).strip() 

                    with c1: st.markdown(f"## {avatar}")
                    with c2:
                        st.markdown(f"**{name}** &nbsp; <span style='color:grey'>{timestamp}</span>", unsafe_allow_html=True)
                        st.markdown(f"{'⭐' * rating_val}")
                        st.write(text_val)
                        
                        # Only show if reply is valid
                        if reply_val and reply_val.lower() != 'nan':
                            st.info(f"**Response from the owner:**\n\n{reply_val}")
                        
                        st.divider()
        else:
            st.info("No reviews yet.")

# === DASHBOARD 2: ADMIN VIEW (Updated with Analytics) ===
with tab_admin:
    st.header("Internal Feedback Monitor")
    
    if st.button("🔄 Refresh Admin Data"): 
        st.rerun()

    data = load_data()
    
    if not data.empty:
        # --- 1. DATA CLEANING (As per Report) ---
        # Filter out rows where the AI reply contains an error message
        if 'ai_reply' in data.columns:
            clean_data = data[~data['ai_reply'].astype(str).str.contains("Error|429|404", case=False, na=False)]
        else:
            clean_data = data
            
        if not clean_data.empty:
            
            # --- 2. ANALYTICS (Bonus Feature) ---
            st.subheader("📊 Analytics Overview")
            
            col1, col2, col3 = st.columns(3)
            total_reviews = len(clean_data)
            
            if 'rating' in clean_data.columns:
                avg_rating = clean_data['rating'].mean()
                col1.metric("Total Reviews", total_reviews)
                col2.metric("Average Rating", f"{avg_rating:.1f} ⭐")
                
                # Count critical issues (1 & 2 stars)
                critical_issues = len(clean_data[clean_data['rating'] <= 2])
                col3.metric("Critical Issues", critical_issues, delta_color="inverse")
            
            st.markdown("---")

            # Visual Charts
            c_chart1, c_chart2 = st.columns(2)
            
            with c_chart1:
                st.caption("Star Rating Distribution")
                if 'rating' in clean_data.columns:
                    rating_counts = clean_data['rating'].value_counts().sort_index()
                    st.bar_chart(rating_counts, color="#FF4B4B") # Red bars

            with c_chart2:
                st.caption("Daily Review Volume")
                if 'timestamp' in clean_data.columns:
                    try:
                        # Ensure date sorting
                        daily_counts = clean_data['timestamp'].value_counts().sort_index()
                        st.line_chart(daily_counts, color="#1F77B4") # Blue line
                    except:
                        st.info("Trend data unavailable.")

            st.markdown("---")

            # --- 3. DATA TABLE (Cleaned) ---
            st.subheader("Recent Submissions")
            st.dataframe(clean_data.sort_index(ascending=False), use_container_width=True)
            
        else:
            st.info("No valid reviews found (all entries may be errors).")
    else:
        st.info("No reviews found.")