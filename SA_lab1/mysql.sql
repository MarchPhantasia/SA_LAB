CREATE TABLE t_chat_history (
    id BIGINT,               
    conversation_id VARCHAR(100) NOT NULL,          
    chat_history TEXT, 
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_usage INT
);
