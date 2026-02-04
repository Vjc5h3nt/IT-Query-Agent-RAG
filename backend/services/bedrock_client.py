"""AWS Bedrock client for LLM and embedding generation."""
import boto3
import json
from typing import List, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class BedrockClient:
    """Client for AWS Bedrock API interactions."""
    
    def __init__(self):
        """Initialize Bedrock runtime client."""
        self.client = boto3.client(
            service_name='bedrock-runtime',
            region_name=settings.aws_region
        )
        self.model_id = settings.aws_bedrock_model_id
        self.embedding_model_id = settings.aws_bedrock_embedding_model_id
        logger.info(f"Initialized Bedrock client with model: {self.model_id}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for given text using Amazon Titan.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            # Titan embedding request format
            request_body = json.dumps({
                "inputText": text
            })
            
            response = self.client.invoke_model(
                modelId=self.embedding_model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding', [])
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        return [self.generate_embedding(text) for text in texts]
    
    def generate_response(
        self,
        user_message: str,
        context: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True
    ) -> str:
        """
        Generate a response using Claude with strict grounding.
        
        Args:
            user_message: Current user message
            context: Retrieved context from RAG
            conversation_history: Previous messages (last 5)
            use_knowledge_base: Whether knowledge base access is enabled
            
        Returns:
            Generated response text
        """
        try:
            # Build conversation with strict grounding system prompt
            if use_knowledge_base:
                system_prompt = """You are a helpful, professional assistant.

CRITICAL RULES:
1. For greetings (e.g., "Hi", "Hello") or casual chat, answer naturally and concisely. DO NOT explain what you can/cannot do or mention "context" or "internal knowledge".
2. For subject-specific or factual questions, use ONLY the provided "Context from knowledge base".
3. If the answer is not in the context, say: "I don't have enough information in my knowledge base to answer that question."
4. DO NOT guess or hallucinate. If details are missing, ask for clarification.
5. Do NOT reference topics not mentioned in THIS session.
6. Be direct and avoid unnecessary preamble."""
            else:
                system_prompt = """You are a helpful assistant. Knowledge base access is DISABLED.

CRITICAL RULES:
1. For greetings or casual chat, answer naturally and concisely. DO NOT explain your constraints.
2. For ANY subject-specific or factual questions, politely state: "Please enable the Knowledge Base in the UI to ask questions about the documents."
3. DO NOT use your own knowledge for factual questions. 
4. DO NOT guess.
5. Do NOT mention why you can't answer in detail unless it's a factual question."""

            # Format messages for Claude with alternating roles strictly enforced
            formatted_messages = []
            
            if conversation_history:
                last_role = None
                for msg in conversation_history:
                    role = msg["role"]
                    content = msg["content"]
                    
                    if not content or not content.strip():
                        continue
                        
                    if role == last_role:
                        # Merge content with previous message of same role
                        formatted_messages[-1]["content"] += f"\n\n{content}"
                        continue
                    
                    formatted_messages.append({
                        "role": role,
                        "content": content
                    })
                    last_role = role
            
            # Prepare current user content
            if use_knowledge_base:
                user_content = f"""Context from knowledge base:
{context if context else "None"}

User question: {user_message}"""
            else:
                user_content = user_message
            
            # Check if we should append or merge with last history message
            if formatted_messages and formatted_messages[-1]["role"] == "user":
                formatted_messages[-1]["content"] += f"\n\n--- Next Question ---\n{user_content}"
            else:
                formatted_messages.append({
                    "role": "user",
                    "content": user_content
                })
            
            # Claude 3 request format
            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.1,  # Low temperature for more factual responses
                "system": system_prompt,
                "messages": formatted_messages
            })
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=request_body,
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            
            # Extract text from Claude response
            assistant_message = response_body.get('content', [{}])[0].get('text', '')
            
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise


# Global Bedrock client instance
bedrock_client = BedrockClient()
