import streamlit as st
import pandas as pd
import google.generativeai as genai
import time
import os
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Page config must be the first Streamlit command
st.set_page_config(page_title="Fynd Reviews", layout="wide")

# --- AUTHENTICATION ---

@st.cache_resource
def get_google_sheet():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Load credentials from secrets.toml
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Connect to the specific sheet
        return client.open("Fynd Review Dashboard").sheet1  
    except Exception:
        return None

# Setup Gemini API
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
elif "GOOGLE_API_KEY" in os.environ:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

def get_gemini_response(prompt):
    try:
        # Using flash-latest for better free tier limits
        model = genai.GenerativeModel("models/gemini-flash-latest")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- DATA FUNCTIONS ---

def load_data():
    sheet = get_google_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            # Normalize headers to lowercase to avoid key errors
            df.columns = [c.lower() for c in df.columns]
            return df
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_entry(rating, text, reply, summary, action):
    sheet = get_google_sheet()
    if not sheet:
        st.error("Database connection failed. Cannot save.")
        return

    # Random placeholders for demo purposes
    fake_names = ["Alex R.", "Sam K.", "Jordan P.", "Casey M.", "Taylor S.", "Priya D.", "Rohan G."]
    fake_avatars = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🐯"]
    
    row = [
        datetime.now().strftime("%Y-%m-%d"), 
        rating,                              
        text,                                
        reply,                               
        summary,                             
        action,                              
        random.choice(fake_names),           
        random.choice(fake_avatars)          
    ]
    
    try:
        sheet.append_row(row)
    except Exception as e:
        st.error(f"Save failed: {e}")

# --- AI LOGIC ---

def generate_ai_content(review_text, rating):
    # 1. Generate polite reply for the user
    reply_prompt = f"""
    You are a business owner. Write a short, professional, grateful response 
    to this customer review: "{review_text}" (Rating: {rating}/5). 
    Max 2 sentences.
    """
    reply = get_gemini_response(reply_prompt)

    # 2. Generate summary/action for admin
    admin_prompt = f"""
    Analyze this review: "{review_text}" (Rating: {rating}/5).
    1. Summarize in 5 words.
    2. Suggest one specific business action.
    
    Format:
    Summary: <text>
    Action: <text>
    """
    analysis = get_gemini_response(admin_prompt)
    
    # Simple parsing logic
    try:
        lines = analysis.split('\n')
        summary = next((line.split(': ')[1] for line in lines if 'Summary:' in line), "General Feedback")
        action = next((line.split(': ')[1] for line in lines if 'Action:' in line), "Review Manually")
    except:
        summary = "Analysis Pending"
        action = "Review Manually"

    return reply, summary, action

# --- MAIN UI ---

st.title("🚀 Fynd Dashboard")

tab_user, tab_admin = st.tabs(["⭐ Public Reviews", "🛡️ Admin Dashboard"])

# === USER TAB ===
with tab_user:
    col_left, col_right = st.columns([1, 2])
    
    # Input Form
    with col_left:
        st.subheader("Rate your experience")
        with st.form("user_form"):
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

    # Display Feed
    with col_right:
        data = load_data()
        
        # Filter out rows with API errors so users don't see them
        if not data.empty and 'ai_reply' in data.columns:
            clean_data = data[~data['ai_reply'].astype(str).str.contains("Error|429|404", case=False, na=False)]
        else:
            clean_data = data
            
        if not clean_data.empty:
            # Show average rating
            if 'rating' in clean_data.columns:
                avg = clean_data['rating'].mean()
                st.markdown(f"### {avg:.1f} ⭐⭐⭐⭐⭐ ({len(clean_data)} reviews)")
            st.divider()
            
            # Render reviews
            for idx, row in clean_data.sort_index(ascending=False).iterrows():
                c1, c2 = st.columns([1, 10])
                
                # Safely get fields
                avatar = row.get('avatar', '👤')
                name = row.get('user_name', 'Anonymous')
                ts = row.get('timestamp', '')
                stars = int(row.get('rating', 5))
                txt = row.get('review_text', '')
                reply = str(row.get('ai_reply', '')).strip()

                with c1: st.markdown(f"## {avatar}")
                with c2:
                    st.markdown(f"**{name}** &nbsp; <span style='color:grey'>{ts}</span>", unsafe_allow_html=True)
                    st.markdown(f"{'⭐' * stars}")
                    st.write(txt)
                    
                    if reply and reply.lower() != 'nan':
                        st.info(f"**Owner Response:**\n\n{reply}")
                    st.divider()
        else:
            st.info("No reviews yet.")

# === ADMIN TAB ===
with tab_admin:
    st.header("Internal Feedback Monitor")
    
    if st.button("🔄 Refresh Data"): 
        st.rerun()

    data = load_data()
    
    if not data.empty:
        # 1. Clean Data (Filter out API errors)
        if 'ai_reply' in data.columns:
            clean_data = data[~data['ai_reply'].astype(str).str.contains("Error|429|404", case=False, na=False)]
        else:
            clean_data = data
            
        if not clean_data.empty:
            
            # 2. Analytics Section
            st.subheader("📊 Analytics Overview")
            
            c1, c2, c3 = st.columns(3)
            total = len(clean_data)
            
            if 'rating' in clean_data.columns:
                avg = clean_data['rating'].mean()
                c1.metric("Total Reviews", total)
                c2.metric("Avg Rating", f"{avg:.1f} ⭐")
                
                # Flag low ratings (1-2 stars)
                issues = len(clean_data[clean_data['rating'] <= 2])
                c3.metric("Critical Issues", issues, delta_color="inverse")
            
            st.markdown("---")

            # Charts
            chart1, chart2 = st.columns(2)
            
            with chart1:
                st.caption("Rating Distribution")
                if 'rating' in clean_data.columns:
                    counts = clean_data['rating'].value_counts().sort_index()
                    st.bar_chart(counts, color="#FF4B4B")

            with chart2:
                st.caption("Daily Volume")
                if 'timestamp' in clean_data.columns:
                    try:
                        dates = clean_data['timestamp'].value_counts().sort_index()
                        st.line_chart(dates, color="#1F77B4")
                    except:
                        st.info("No trend data.")

            st.markdown("---")

            # 3. Raw Data Table
            st.subheader("Recent Submissions")
            st.dataframe(clean_data.sort_index(ascending=False), use_container_width=True)
            
        else:
            st.info("No valid data found (check for API errors).")
    else:
        st.info("No reviews found.")