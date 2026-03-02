@echo off
:: Run the AI Video Style Analyzer using the local venv
echo Starting AI Video Style Analyzer...
cd /d "%~dp0"
.\venv\Scripts\streamlit run app.py
pause
