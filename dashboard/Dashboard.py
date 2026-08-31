"""
SpacePoint - App Entry Point / Navigation
Author: Kommal

This file no longer contains page content - it only defines the
sidebar structure: two labeled sections (the core mission pipeline,
and a set of specialized geospatial/imagery tools), each page's
sidebar title and icon, and page order. The actual Mission Dashboard
content that used to live here now lives in
pages/0_Mission_Dashboard.py, alongside the other pages.

Icons are Streamlit's built-in Material Symbols (":material/name:") -
simple monochrome line icons, no emoji, no custom color.
"""

import streamlit as st

pg = st.navigation(
    {
        "Mission Pipeline": [
            st.Page(
                "pages/1_Data_Quality.py",
                title="Quality Check",
                icon=":material/fact_check:",
            ),
            st.Page(
                "pages/2_Data_Cleaning.py",
                title="Data Cleaning",
                icon=":material/cleaning_services:",
            ),
            st.Page(
                "pages/0_Mission_Dashboard.py",
                title="Mission Dashboard",
                icon=":material/dashboard:",
                default=True,
            ),
            st.Page(
                "pages/5_Report_Generator.py",
                title="Mission Report",
                icon=":material/description:",
            ),
        ],
        "Specialized Tools": [
            st.Page(
                "pages/3_Mission_Map.py",
                title="Mission Map",
                icon=":material/map:",
            ),
            st.Page(
                "pages/4_Image_Tool.py",
                title="Image Analysis",
                icon=":material/image_search:",
            ),
        ],
    }
)

pg.run()