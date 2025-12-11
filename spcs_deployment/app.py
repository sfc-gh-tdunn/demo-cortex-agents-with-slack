from typing import Any
import os
import re
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import snowflake.connector
from snowflake.core import Root
from dotenv import load_dotenv
from snowflake.snowpark import Session
import cortex_chat

load_dotenv()

ACCOUNT = os.getenv("ACCOUNT")
HOST = os.getenv("HOST")
USER = os.getenv("DEMO_USER")
ROLE = os.getenv("DEMO_USER_ROLE")
WAREHOUSE = os.getenv("WAREHOUSE")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")
PAT = os.getenv("PAT")

DEBUG = True

# Define whitelist of allowed users by their Slack user IDs
ALLOWED_USERS = {
    "U08PNH92YSC"
}

app = App(token=SLACK_BOT_TOKEN)
messages = []

planning_steps_data = {}

@app.event("app_mention")
def handle_app_mention(ack, event, say, client, body):
    ack()
    user_id = event.get('user')
    if user_id not in ALLOWED_USERS:
        say("🚫 Sorry, you are not authorized to use this bot.")
        return

    thread = threading.Thread(
        target=handle_message_event,
        kwargs={
            "event": event,
            "say": say,
            "client": client,
            "body": body
        }
    )
    thread.start()

@app.message(re.compile(".*"))
def handle_direct_message(ack, message, say, client, body):
    ack()
    user_id = message.get('user')
    if user_id not in ALLOWED_USERS:
        say("🚫 Sorry, you are not authorized to use this bot.")
        return

    if message.get('channel_type') == 'im':
        thread = threading.Thread(
            target=handle_message_event,
            kwargs={
                "event": message,
                "say": say,
                "client": client,
                "body": body
            }
        )
        thread.start()
def handle_message_event(event, say, client, body):
    try:
        user_message = event.get('text', '').strip()
        if not user_message:
            return
        
        user_message = re.sub(r'<@\w+>', '', user_message).strip()
        
        if not user_message:
            say("👋 Hi! Ask me any question about your data and I'll help you analyze it using Snowflake Cortex.")
            return
        
        global CORTEX_APP
        if not CORTEX_APP:
            say("❌ Cortex Agent not initialized. Please check your configuration.")
            return
        
        CORTEX_APP.set_slack_say_function(say)
        CORTEX_APP.set_slack_app(app, event.get('channel'))
        
        say(
            text="🚀 Starting Cortex Agent...",
            blocks=[
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":snowflake: *Snowflake Cortex Agent* is processing your request...\n_You'll see real-time updates as the agent works!_",
                    }
                },
                {"type": "divider"},
            ]
        )
        
        response = CORTEX_APP.chat(user_message)
        
        display_agent_response(response, say)
        
    except Exception as e:
        error_info = f"{type(e).__name__} at line {e.__traceback__.tb_lineno} of {__file__}: {e}"
        print(f"❌ Error in handle_message_event: {error_info}")
        say(f"❌ Sorry, there was an error processing your message: {str(e)}")
@app.action("show_planning_details")
def handle_planning_details_toggle(ack, body, say):
    ack()
    
    try:
        action_value = body["actions"][0]["value"]
        message_ts = body["message"]["ts"]
        channel_id = body["channel"]["id"]
        
        try:
            timeline = getattr(CORTEX_APP, 'timeline', [])
            if not timeline:
                steps = getattr(CORTEX_APP, 'planning_steps', [])
                thinking_steps = getattr(CORTEX_APP, 'thinking_steps', [])
            else:
                steps = []
                thinking_steps = []
        except:
            timeline = []
            steps = planning_steps_data.get('steps', [])
            thinking_steps = []
        
        if action_value == "show":
            blocks = [{
                "type": "section",
                "text": {"type": "mrkdwn","text": "*🤔 Thinking...* ✅ *Completed!*"}
            }]
            
            combined_steps = []
            if timeline:
                for event in timeline:
                    if event['type'] == 'status':
                        combined_steps.append(f" {event['content']}")
                    elif event['type'] == 'thinking':
                        combined_steps.append(f" {event['content']}")
            else:
                if steps:
                    for step in steps:
                        combined_steps.append(f" {step}")
                if thinking_steps:
                    for thinking in thinking_steps:
                        combined_steps.append(f" {thinking}")
            
            if combined_steps:
                header = "*Thinking Steps:*\n"
                max_content_length = 2950 - len(header)
                
                steps_text = ""
                truncated = False
                for i, step in enumerate(combined_steps):
                    step_line = f"• {step}\n"
                    if len(steps_text) + len(step_line) <= max_content_length:
                        steps_text += step_line
                    else:
                        truncated = True
                        break
                steps_text = steps_text.rstrip('\n')
                if truncated:
                    remaining_count = len(combined_steps) - i
                    steps_text += f"\n\n_... and {remaining_count} more items (truncated for display)_"
                
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn","text": f"{header}{steps_text}"}
                })
            
            try:
                sql_queries = getattr(CORTEX_APP, 'sql_queries', [])
                verified_query_used = getattr(CORTEX_APP, 'verified_query_used', False)
                
                if sql_queries:
                    num_queries = len(sql_queries)
                    blocks.extend([
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*💾 SQL Queries:*\nCortex Analyst used {num_queries} SQL {'query' if num_queries == 1 else 'queries'}"
                            }
                        }
                    ])
                    
                    for i, sql_query in enumerate(sql_queries, 1):
                        is_verified = verified_query_used and (i == 1 or num_queries == 1)
                        query_header = f"*💾 SQL Query {i}:*"
                        if is_verified:
                            query_header += " :verified: Answer accuracy verified by agent owner"
                        if len(sql_query) > 2800:
                            displayed_sql = sql_query[:2800] + "...\n-- (SQL truncated for display)"
                        else:
                            displayed_sql = sql_query
                        
                        blocks.extend([
                            {"type": "section","text": {"type": "mrkdwn","text": query_header}},
                            {"type": "section","text": {"type": "mrkdwn","text": f"``````"}}
                        ])
                        if i < len(sql_queries):
                            blocks.append({"type": "divider"})
                    
                    blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn","text": "ℹ️ All SQL queries were already executed by Cortex during analysis. Results are included in the response above."}]
                    })
            except:
                pass
            
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text","text": "🔽 Hide Details"},
                    "action_id": "show_planning_details",
                    "value": "hide"
                }]
            })
        else:
            if timeline:
                step_count = len(timeline)
            else:
                step_count = (len(steps) if steps else 0) + (len(thinking_steps) if thinking_steps else 0)
            additional_info = []
            try:
                has_verification = getattr(CORTEX_APP, 'verification_info', {}) or getattr(CORTEX_APP, 'verified_query_used', False)
                sql_queries = getattr(CORTEX_APP, 'sql_queries', [])
                
                if has_verification and sql_queries:
                    query_count = len(sql_queries)
                    additional_info.append(f":verified: answer accuracy verified by agent owner for {query_count} SQL {'query' if query_count == 1 else 'queries'}")
                elif has_verification:
                    additional_info.append(":verified: answer accuracy verified by agent owner")
                elif sql_queries:
                    query_count = len(sql_queries)
                    additional_info.append(f"{query_count} SQL {'query' if query_count == 1 else 'queries'}")
            except:
                pass
            
            summary_text = f"_Finished {step_count} steps"
            if additional_info:
                summary_text += f" • Includes {' and '.join(additional_info)}"
            summary_text += "_"
            
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn","text": f"*🤔 Thinking...* ✅ *Completed!*\n\n{summary_text}"}
                },
                {
                    "type": "actions",
                    "elements": [{
                        "type": "button",
                        "text": {"type": "plain_text","text": "📋 Show Details"},
                        "action_id": "show_planning_details",
                        "value": "show"
                    }]
                }
            ]
        
        app.client.chat_update(channel=channel_id, ts=message_ts, text="🤔 Planning details", blocks=blocks)
        
    except Exception as e:
        print(f"Error handling planning details toggle: {e}")
        say(f"❌ Error toggling planning details: {e}")

def smart_truncate(text, max_length=300, suffix="..."):
    """Smart truncation that preserves word and sentence boundaries."""
    if len(text) <= max_length:
        return text
    sentences = text.split('. ')
    if len(sentences) > 1:
        truncated = ""
        for sentence in sentences:
            test_text = truncated + sentence + ". "
            if len(test_text) + len(suffix) <= max_length:
                truncated = test_text
            else:
                break
        if truncated.strip():
            return truncated.strip() + suffix
    words = text.split()
    truncated = ""
    for word in words:
        test_text = truncated + word + " "
        if len(test_text) + len(suffix) <= max_length:
            truncated = test_text
        else:
            break
    return truncated.strip() + suffix if truncated.strip() else text[:max_length-len(suffix)] + suffix

def ask_agent(prompt, say):
    resp = CORTEX_APP.chat(prompt)
    return resp

def format_text_for_slack(text):
    if not text:
        return text
    try:
        import re
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        text = re.sub(r'__(.*?)__', r'*\1*', text)
        text = re.sub(r'(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)', r'_\1_', text)
        return text
    except Exception as e:
        print(f"❌ Error formatting text: {e}")
        return text

def format_dataframe_for_slack(df):
    try:
        display_df = df.head(20) if len(df) > 20 else df
        if len(df) > 20:
            table_str = display_df.to_string(index=False, max_colwidth=30)
            table_str += f"\n\n... and {len(df) - 20} more rows"
        else:
            table_str = display_df.to_string(index=False, max_colwidth=30)
        return table_str
    except Exception as e:
        print(f"❌ Error formatting DataFrame: {e}")
        return "Error formatting data for display"

def display_agent_response(content, say):
    try:
        if content.get('text'):
            formatted_text = format_text_for_slack(content['text'])
            say(
                text="🎯 Final Response",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🎯 Snowflake Cortex Agent Response:*\n{formatted_text}"
                        }
                    }
                ]
            )
        if content.get('verification_info') or content.get('verified_query_used'):
            CORTEX_APP.verification_info = content.get('verification_info', {})
            CORTEX_APP.verified_query_used = content.get('verified_query_used', False)
        if content.get('sql_queries'):
            CORTEX_APP.sql_queries = content['sql_queries']
        if content.get('citations') and content['citations']:
            formatted_citations = format_text_for_slack(content['citations'])
            say(
                text="📚 Citations",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📚 Citations:*\n_{formatted_citations}_"
                        }
                    }
                ]
            )
        if content.get('suggestions'):
            formatted_suggestions = [format_text_for_slack(suggestion) for suggestion in content['suggestions'][:3]]
            suggestions_text = "\n".join(f"• {suggestion}" for suggestion in formatted_suggestions)
            say(
                text="💡 Suggestions",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*💡 Follow-up Suggestions:*\n{suggestions_text}"
                        }
                    }
                ]
            )
    except Exception as e:
        error_info = f"{type(e).__name__} at line {e.__traceback__.tb_lineno} of {__file__}: {e}"
        print(f"❌ Error in display_agent_response: {error_info}")
        say(
            text="❌ Display error",
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Error displaying response*\n``````"
                }
            }]
        )

def get_snowflake_connection():
    try:
        print("🔗 Attempting Snowflake connection with PAT authentication...")
        account = ACCOUNT
        if not account:
            if HOST:
                account = HOST.split('.')[0]
                print(f"   📋 Extracted account from host: {account}")
        try:
            conn = snowflake.connector.connect(
                user=USER,
                password=PAT,
                account=account,
                warehouse=WAREHOUSE,
                role=ROLE
            )
            cursor = conn.cursor()
            cursor.execute("SELECT CURRENT_VERSION()")
            result = cursor.fetchone()
            cursor.close()
            print(f"   ✅ PAT authentication successful! Snowflake version: {result[0]}")
            return conn
        except Exception as pat_error:
            print(f"   ❌ PAT authentication failed: {pat_error}")
            return None
    except Exception as e:
        print(f"   ❌ Failed to connect to Snowflake: {e}")
        return None

def init():
    conn = get_snowflake_connection()
    cortex_app = cortex_chat.CortexChat(
        AGENT_ENDPOINT, 
        PAT
    )
    print("🚀 Initialization complete")
    return conn, cortex_app

if __name__ == "__main__":
    CONN, CORTEX_APP = init()
    if CONN:
        Root = Root(CONN)
        SocketModeHandler(app, SLACK_APP_TOKEN).start()
