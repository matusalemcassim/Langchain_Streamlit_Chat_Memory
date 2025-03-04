# LangChain Streamlit Chat with Memory

This repository demonstrates how to build a chatbot using **LangChain** and **Streamlit**, incorporating chat history memory for contextual responses. 

## 🚀 Features
- 🗣️ Conversational chatbot using LangChain
- 💾 Chat memory to maintain context across user interactions
- 🎨 Simple and interactive Streamlit UI
- 🔌 Easily extensible for various applications

## 📂 Repository Structure
📦 Langchain_Streamlit_Chat_Memory ├── 📜 main.py # Main Streamlit app ├── 📜 chatbot.py # Chatbot logic using LangChain ├── 📜 memory.py # Chat memory management ├── 📜 requirements.txt # Dependencies └── 📜 README.md # This document

bash
Copy
Edit

## 🛠️ Installation & Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/matusalemcassim/Langchain_Streamlit_Chat_Memory.git
   cd Langchain_Streamlit_Chat_Memory
   ```
   
2. **Create a Virtual Environment (Optional)**
  ```bash
  python -m venv venv
  source venv/bin/activate  # Mac/Linux
  venv\Scripts\activate     # Windows
  ```
3. Install Dependencies
Once inside the project directory, install all required dependencies:
```bash
  pip install -r requirements.txt
```
4. Run the Chatbot
Launch the Streamlit chatbot application by running:
  ```bash
streamlit run main.py
  ```

⚙️ Configuration
- Ensure main.py and chatbot.py are properly configured for your use case.
- Modify memory.py if you want to customize how chat history is stored.
  
📌 Usage
- Start the chatbot by running streamlit run main.py.
- Type a message in the chat input.
- The chatbot will remember past interactions and provide responses with context.
  
🛠️ Customization
- You can modify chatbot.py to integrate different LLM models.
- Adjust memory.py for various chat memory strategies.
  
🤝 Contributions

Feel free to fork this repository, submit issues, or create pull requests!

📜 License

This project is licensed under the MIT License.
