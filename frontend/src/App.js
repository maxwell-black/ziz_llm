// frontend/src/App.js
import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// Use relative path as Flask backend will serve API from the same origin in Cloud Run
const SERVER_URL = '/chat';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null); // Ref to scroll to bottom

  // Function to scroll to the bottom of the chat messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Scroll to bottom whenever messages update
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleInputChange = (event) => {
    setInput(event.target.value);
  };

  const handleSendMessage = async (event) => {
     // Allow sending via Enter key or button click
    if (event.key && event.key !== 'Enter') return;
    if (!input.trim()) return; // Don't send empty messages

    const userMessage = { text: input, sender: 'user' };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    const currentInput = input; // Store input before clearing
    setInput(''); // Clear input field immediately
    setIsLoading(true);

    try {
      const response = await fetch(SERVER_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: currentInput }),
      });

      if (!response.ok) {
        // Try to get error message from server response body
        let errorMsg = `HTTP error! Status: ${response.status}`;
        try {
           const errData = await response.json();
           errorMsg = errData.error || errorMsg;
        } catch(e) {
           // Ignore if response body isn't valid JSON
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      // Handle potential undefined answer
      const botAnswer = data.answer || "Received no answer from bot.";
      const botMessage = { text: botAnswer, sender: 'bot' };
      setMessages(prevMessages => [...prevMessages, botMessage]);

    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = { text: `Error: ${error.message || 'Could not connect.'}`, sender: 'error' };
      // Add error message to chat
      setMessages(prevMessages => [...prevMessages, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Ž</h1>
      </header>
      <div className="chat-window">
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.sender}`}>
               {/* Basic formatting for newlines */}
               {msg.text.split('\n').map((line, i) => (
                 <React.Fragment key={i}>
                   {line}
                   <br />
                 </React.Fragment>
               ))}
            </div>
          ))}
          {isLoading && <div className="message bot loading"><span>.</span><span>.</span><span>.</span></div>}
          {/* Empty div to target for scrolling */}
          <div ref={messagesEndRef} />
        </div>
        <div className="input-area">
          <input
            type="text"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleSendMessage} // Send on Enter key
            placeholder="..."
            disabled={isLoading}
            aria-label="Chat input" // Accessibility
          />
          <button onClick={handleSendMessage} disabled={isLoading || !input.trim()}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;