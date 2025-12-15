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
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Fynd Review Dashboard").sheet1  
        return sheet
    except Exception as e:
        return None

# --- AUTHENTICATION (Gemini AI) ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    if "GOOGLE_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

def get_gemini_response(prompt):
    try:
        model = genai.GenerativeModel("models/gemini-flash-latest")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- DATA HANDLING ---

def load_data():
    sheet = get_google_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            # Force lowercase columns for safety
            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            return pd.DataFrame()
    return pd.DataFrame()

def save_entry(rating, text, reply, summary, action):
    sheet = get_google_sheet()
    if not sheet:
        st.error("Database connection failed. Cannot save.")
        return

    fake_names = ["Alex R.", "Sam K.", "Jordan P.", "Casey M.", "Taylor S.", "Priya D.", "Rohan G."]
    fake_avatars = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🐯"]
    
    new_row = [
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
        sheet.append_row(new_row)
    except Exception as e:
        st.error(f"Failed to save data: {e}")

# --- AI GENERATION ---
def generate_ai_content(review_text, rating):
    reply_prompt = f"""
    You are a business owner replying to a customer review. 
    Review: "{review_text}" (Rating: {rating}/5).
    Write a short, professional, and grateful response. Max 2 sentences.
    """
    reply = get_gemini_response(reply_prompt)

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
            if 'ai_reply' in data.columns:
                clean_data = data[~data['ai_reply'].astype(str).str.contains("Error|429|404", case=False, na=False)]
            else:
                clean_data = data
            
            if not clean_data.empty:
                if 'rating' in clean_data.columns:
                    avg_rating = clean_data['rating'].mean()
                    st.markdown(f"### {avg_rating:.1f} ⭐⭐⭐⭐⭐ ({len(clean_data)} reviews)")
                st.divider()
                
                for index, row in clean_data.sort_index(ascending=False).iterrows():
                    c1, c2 = st.columns([1, 10])
                    
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
                        
                        if reply_val and reply_val.lower() != 'nan':
                            st.info(f"**Response from the owner:**\n\n{reply_val}")
                        
                        st.divider()
        else:
            st.info("No reviews yet.")

# === DASHBOARD 2: ADMIN VIEW ===
with tab_admin:
    st.header("Internal Feedback Monitor")
    
    # Simple Refresh Button (No more Delete button)
    if st.button("🔄 Refresh Admin Data"): 
        st.rerun()

    data = load_data()
    if not data.empty:
        st.dataframe(data.sort_index(ascending=False), use_container_width=True)
    else:
        st.info("No reviews found.")