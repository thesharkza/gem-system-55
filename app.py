# ==========================================
# 🎨 0.1 LIMITLESS DASHBOARD UI ENGINE (Light Theme)
# ==========================================
st.markdown("""
<style>
    /* บังคับพื้นหลังให้เป็นสีเทาอ่อนแบบ Limitless */
    .stApp {
        background-color: #f4f5f7;
    }

    /* 1. จัดการพื้นที่ขอบ ให้ดูเป็นระเบียบ */
    div.block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }
    
    /* 2. ซ่อนแถบ Header ของ Streamlit */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* 3. ตกแต่งกรอบ Expander ให้เป็นสไตล์ Panel สีขาว ขอบบาง เงาอ่อนๆ */
    div[data-testid="stExpander"] {
        background-color: #ffffff !important;
        border-radius: 6px !important;
        border: 1px solid #cfd8dc !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    div[data-testid="stExpander"] summary {
        background-color: #f8f9fa !important;
        border-bottom: 1px solid #eceff1 !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 10px 15px !important;
    }
    div[data-testid="stExpander"] summary p {
        color: #333333 !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    /* 4. ตกแต่งช่องกรอกข้อมูล (Inputs) สไตล์ Bootstrap */
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
        border-radius: 4px !important;
        background-color: #ffffff !important;
        border: 1px solid #cfd8dc !important;
        transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
    }
    div[data-baseweb="input"] > div:focus-within {
        border-color: #2196f3 !important;
        box-shadow: 0 0 0 0.2rem rgba(33, 150, 243, 0.25) !important;
    }
    
    /* สีตัวอักษรใน Input */
    input, textarea {
        color: #333333 !important;
    }

    /* 5. ตกแต่งปุ่มกด (Secondary Buttons) */
    button[kind="secondary"] {
        border-radius: 4px !important;
        border: 1px solid #cfd8dc !important;
        background-color: #ffffff !important;
        color: #333333 !important;
        font-weight: 500 !important;
        transition: all 0.2s ease;
    }
    button[kind="secondary"]:hover {
        background-color: #eceff1 !important;
        border-color: #b0bec5 !important;
    }

    /* 6. ตกแต่งปุ่มหลัก (Primary Button) สไตล์ Limitless Blue */
    button[kind="primary"] {
        border-radius: 4px !important;
        background-color: #2196f3 !important; /* สีฟ้าน้ำเงิน */
        color: #ffffff !important;
        font-weight: 600 !important;
        border: none !important;
        box-shadow: 0 2px 5px rgba(33, 150, 243, 0.3) !important;
        transition: all 0.2s ease;
    }
    button[kind="primary"]:hover {
        background-color: #1e88e5 !important;
        box-shadow: 0 4px 8px rgba(33, 150, 243, 0.4) !important;
    }
    button[kind="primary"]:active {
        transform: translateY(1px);
    }

    /* 7. ปรับสไตล์ตัวเลข Metrics (เกจวัด) ให้อ่านง่าย */
    div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: #333 !important;
        text-shadow: none !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #78909c !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        font-size: 0.85rem !important;
    }
    
    /* 8. ปรับแต่ง Tabs ให้ดูเป็น Navbar คลีนๆ */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        color: #607d8b !important;
        border-radius: 0 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid transparent !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #2196f3 !important;
        border-bottom: 2px solid #2196f3 !important;
    }

    /* 9. เปลี่ยนสีหัวข้อ (Headers) ทั้งหมดเป็นสีเข้ม */
    h1, h2, h3, h4, h5, h6 {
        color: #263238 !important;
        font-weight: 600 !important;
    }

    /* 10. ตกแต่ง Sidebar ให้เป็นโทนสีเข้ม (Limitless Dark Sidebar) */
    [data-testid="stSidebar"] {
        background-color: #263238 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
        color: #cfd8dc !important;
    }
</style>
""", unsafe_allow_html=True)
