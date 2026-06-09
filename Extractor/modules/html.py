
import json
import re
import os
import asyncio
from collections import defaultdict
import unicodedata
import string
from pyrogram import filters
from pyrogram.errors import FloodWait, RPCError
from Extractor import app
from config import CHANNEL_ID

appname = "HTMLConverter"
txt_dump = CHANNEL_ID
lock = asyncio.Lock()  # Lock for synchronizing Telegram session access

async def safe_send_message(chat_id, text, client):
    """Safely send a message with retry and lock."""
    async with lock:
        for attempt in range(3):
            try:
                return await client.send_message(chat_id, text)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except RPCError as e:
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
        raise Exception("Failed to send message after retries")

async def safe_edit_message(message, text, client):
    """Safely edit a message with retry and lock."""
    async with lock:
        for attempt in range(3):
            try:
                return await message.edit(text)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except RPCError as e:
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        raise Exception("Failed to edit message after retries")

async def safe_send_document(chat_id, file_path, caption, client):
    """Safely send a document with retry and lock."""
    async with lock:
        for attempt in range(3):
            try:
                return await client.send_document(chat_id, file_path, caption=caption)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except RPCError as e:
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        raise Exception("Failed to send document after retries")

async def safe_forward_message(chat_id, from_chat_id, message_id, client):
    """Safely forward a message with retry and lock."""
    async with lock:
        for attempt in range(3):
            try:
                return await client.forward_messages(chat_id, from_chat_id, message_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except RPCError as e:
                if "Connection is closed" in str(e):
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        raise Exception("Failed to forward message after retries")

def sanitize_filename(filename):
    """Sanitize the filename by removing or replacing special characters."""
    # Normalize Unicode characters (e.g., convert Hindi characters to ASCII equivalents)
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
    # Replace spaces and invalid characters with underscores
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c if c in valid_chars else '_' for c in filename)
    return filename

def count_links(file_path):
    """Count links by type in the input text file."""
    link_counts = defaultdict(int)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                link_counts['total'] += 1
                if ".mp4" in line:
                    link_counts['.mp4'] += 1
                elif ".pdf" in line:
                    link_counts['.pdf'] += 1
                elif ".ws" in line:
                    link_counts['.ws'] += 1
                elif ".m3u8" in line:
                    link_counts['.m3u8'] += 1
    except Exception as e:
        print(f"Error counting links in {file_path}: {e}")
        raise
    return link_counts

def convert_to_json_data(file_path):
    """Convert text file to JSON data, grouping URLs by folder name or default folders."""
    data = defaultdict(list)  # Use defaultdict to avoid manual key initialization
    failed_links = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    print(f"Processing line: {line}")
                    # Match lines with either (folder_name) or [folder_name]
                    match = re.match(r'(?:\((.*?)\)|\[(.*?)\])(.*): (.*)', line)
                    if match:
                        # Extract folder_name from either group 1 (parentheses) or group 2 (brackets)
                        folder_name = match.group(1) if match.group(1) else match.group(2)
                        title = match.group(3).strip()
                        url = match.group(4).strip()
                        data[folder_name].append(f"{title}: {url}")
                    else:
                        # No folder specified, categorize based on URL type
                        match_no_folder = re.match(r'(.*): (.*)', line)
                        if match_no_folder:
                            title = match_no_folder.group(1).strip()
                            url = match_no_folder.group(2).strip()
                            if ".pdf" in url:
                                folder_name = "PDFs"
                            elif ".mp4" in url or ".m3u8" in url:
                                folder_name = "Videos"
                            else:
                                folder_name = "Others"
                            data[folder_name].append(f"{title}: {url}")
                        else:
                            print(f"Invalid line format: {line}")
                            failed_links.append(line)
                except Exception as e:
                    print(f"Error processing line: {line}. Error: {e}")
                    failed_links.append(line)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        raise
    
    return dict(data), failed_links

def generate_html(data, output_file_path, input_file_name, failed_links):
    """Generate HTML file from JSON data and count output links."""
    output_link_counts = defaultdict(int)
    
    html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{input_file_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            color: #333;
            padding: 20px;
            margin: 0;
            overflow-y: scroll;
            overflow-x: hidden;
            height: 100vh;
        }}
        h1 {{
            color: #FFA500;
            text-align: center;
            border-bottom: 2px solid #FFA500;
        }}
        .section-button {{
            display: block;
            width: 100%;
            padding: 15px;
            margin: 10px 0;
            font-size: 1.2em;
            text-align: center;
            color: white;
            background-color: #1E90FF;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }}
        .section-button:hover {{
            background-color: #007BFF;
        }}
        .section {{
            display: none;
        }}
        ul {{
            list-style-type: none;
            padding: 0;
        }}
        li {{
            background-color: #ffffff;
            margin: 10px 0;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.15);
            font-size: 1.1em;
        }}
        .label {{
            font-weight: bold;
            display: block;
        }}
        .video-link {{
            color: #32CD32;
            text-decoration: none;
        }}
        .pdf-link {{
            color: #FFD700;
            text-decoration: none;
        }}
        .test-series-link {{
            color: #FF6347;
            text-decoration: none;
        }}
        .other-link {{
            color: #333;
            text-decoration: none;
        }}
        .link:hover {{
            text-decoration: underline;
        }}
        .author-link {{
            color: #FFA500;
            font-weight: bold;
            font-size: 1.5em;
            text-decoration: none;
        }}
        .float-name {{
            position: fixed;
            bottom: 10px;
            left: 10px;
            font-size: 40px;
            color: #FFA500;
            animation: floatName 10s linear infinite;
        }}
        @keyframes floatName {{
            0% {{ bottom: 10px; left: 10px; }}
            50% {{ bottom: calc(100% - 30px); left: calc(100% - 100px); }}
            100% {{ bottom: 10px; left: 10px; }}
        }}
        .welcome-message {{
            text-align: center;
            font-size: 2em;
            color: #FF4500;
            margin-bottom: 20px;
        }}
        .flower {{
            position: absolute;
            top: -50px;
            width: 50px;
            height: 50px;
            background-image: url('https://www.pngitem.com/pimgs/m/67-673420_pink-flower-flower-clipart-rose-flower-png-transparent-png.png');
            background-size: cover;
            animation: fall linear infinite;
        }}
        @keyframes fall {{
            0% {{ transform: translateY(0) rotate(0deg); opacity: 1; }}
            100% {{ transform: translateY(100vh) rotate(360deg); opacity: 0; }}
        }}
    </style>
    <script>
        function toggleSection(sectionId) {{
            const section = document.getElementById(sectionId);
            if (section.style.display === 'none' || section.style.display === '') {{
                section.style.display = 'block';
            }} else {{
                section.style.display = 'none';
            }}
        }}
        function createFlower() {{
            const flower = document.createElement('div');
            flower.classList.add('flower');
            flower.style.left = Math.random() * 100 + 'vw';
            flower.style.animationDuration = Math.random() * 3 + 2 + 's';
            document.body.appendChild(flower);
            setTimeout(() => {{ flower.remove(); }}, 5000);
        }}
        function startFlowerRain() {{ setInterval(createFlower, 300); }}
        window.onload = () => {{
            alert('THIS IS FREE BATCH FROM RAJASTHANI KING !');
            startFlowerRain();
        }}
    </script>
<//HEAD>
<body>
    <h1>{input_file_name}</h1>
    <div class="welcome-message">THIS IS FREE BATCH FROM RAJASTHANI KING !</div>
    <p>JOIN TELEGRAM: <a href='https://t.me/+5T4l-2VPfDo3Mjhl' target='_blank' class='author-link'>RAJASTHANI KING</a></p>
'''

    try:
        for folder_name, contents in data.items():
            html_content += f'<button class="section-button" onclick="toggleSection(\'{folder_name}\')">{folder_name}</button>'
            html_content += f'<div id="{folder_name}" class="section"><ul>'
            for index, content in enumerate(contents, 1):
                try:
                    video_name, video_url = content.split(':', 1)
                    video_name = video_name.strip()
                    video_url = video_url.strip()
                    if ".m3u8" in video_url or ".mp4" in video_url:
                        label = 'Video'
                        link_class = "video-link"
                        output_link_counts['.mp4'] += 1 if ".mp4" in video_url else 0
                        output_link_counts['.m3u8'] += 1 if ".m3u8" in video_url else 0
                    elif ".pdf" in video_url:
                        label = 'PDF'
                        link_class = "pdf-link"
                        output_link_counts['.pdf'] += 1
                    elif ".ws" in video_url:
                        label = 'Test Series'
                        link_class = "test-series-link"
                        output_link_counts['.ws'] += 1
                    else:
                        label = 'Other'
                        link_class = "other-link"
                    html_content += (
                        f'<li><span class="label">{label}</span>'
                        f'<span class="number">{index}.</span> '
                        f'<a class="{link_class}" href="{video_url}" target="_blank">{video_name}</a></li>'
                    )
                    output_link_counts['total'] += 1
                except Exception as e:
                    print(f"Error processing link: {content}. Error: {e}")
                    failed_links.append(content)
            html_content += '</ul></div>'

        html_content += '''
<div class="float-name">@Extract_by_king_bot</div>
</body>
</html>
'''

        with open(output_file_path, 'w', encoding='utf-8') as file:
            file.write(html_content)
    except Exception as e:
        print(f"Error generating HTML: {e}")
        raise
    
    return output_link_counts

@app.on_message(filters.command(["html"]))
async def handle_html_logic(client, m):
    """Handle the /html command to convert a text file to JSON and HTML."""
    editable = await safe_send_message(
        m.chat.id,
        "Please send a .txt file with lines in the format (folder_name)title: url or [folder_name]title: url.\n"
        "Lines without folders will be categorized as Videos (.mp4, .m3u8), PDFs (.pdf), or Others.\n"
        "I'll convert it to JSON and HTML.",
        client
    )

    # Wait for the user to send a document
    try:
        input_msg = await client.listen(chat_id=m.chat.id, filters=filters.document)
    except Exception as e:
        await safe_edit_message(editable, f"Error waiting for document: {e}", client)
        return

    if not input_msg.document:
        await safe_edit_message(editable, "No document received. Please send a .txt file.", client)
        if input_msg:
            await input_msg.delete()
        return

    document = input_msg.document
    if not document.file_name.endswith('.txt'):
        await safe_edit_message(editable, "Please send a .txt file.", client)
        await input_msg.delete()
        return

    await safe_edit_message(editable, "Processing your file...", client)
    
    # Sanitize the file name to handle special characters
    original_file_name = document.file_name
    sanitized_file_name = sanitize_filename(original_file_name)
    
    # Download the document using client.download_media and capture the actual path
    try:
        downloaded_path = await client.download_media(input_msg, file_name=sanitized_file_name)
        input_file_path = downloaded_path if downloaded_path else sanitized_file_name
        print(f"Downloaded file path: {input_file_path}")
    except Exception as e:
        await safe_edit_message(editable, f"Failed to download file: {e}", client)
        await input_msg.delete()
        return

    # Send the downloaded .txt file to the txt_dump channel
    try:
        await safe_send_document(
            txt_dump,  # Send to CHANNEL_ID
            input_file_path,
            f"Received .txt file: {original_file_name} from user {m.from_user.id}",
            client
        )
    except Exception as e:
        await safe_edit_message(editable, f"Error sending .txt file to channel: {e}", client)
        await input_msg.delete()
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        return

    # Use the sanitized file name for output files, but keep the original name for display
    json_file_path = os.path.splitext(sanitized_file_name)[0] + '.json'
    html_file_path = os.path.splitext(sanitized_file_name)[0] + '.html'
    failed_file_path = "failed.txt"

    # Count input links
    try:
        input_link_counts = count_links(input_file_path)
    except Exception as e:
        await safe_edit_message(editable, f"Error processing input file: {e}", client)
        await input_msg.delete()
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        return

    # Convert text to JSON and get failed links
    try:
        json_data, failed_links = convert_to_json_data(input_file_path)
    except Exception as e:
        await safe_edit_message(editable, f"Error converting to JSON: {e}", client)
        await input_msg.delete()
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        return

    # Save JSON to file
    try:
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(json_data, json_file, ensure_ascii=False, indent=4)
    except Exception as e:
        await safe_edit_message(editable, f"Error saving JSON file: {e}", client)
        await input_msg.delete()
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        return

    # Generate HTML and count output links
    try:
        output_link_counts = generate_html(json_data, html_file_path, original_file_name, failed_links)
    except Exception as e:
        await safe_edit_message(editable, f"Error generating HTML: {e}", client)
        await input_msg.delete()
        for path in [input_file_path, json_file_path]:
            if os.path.exists(path):
                os.remove(path)
        return

    # Prepare caption
    try:
        user = await client.get_users(m.from_user.id)
        credit = f"[{user.first_name}](tg://user?id={m.from_user.id})\n\n"
        caption = (
            f"**APP NAME :** {appname} \n\n"
            f"**File Name :** {original_file_name} \n\n"
            f"TOTAL LINK - {input_link_counts['total']} \n"
            f"Video Links - {output_link_counts['.mp4'] + output_link_counts['.m3u8']} \n"
            f"Total Pdf - {output_link_counts['.pdf']} \n"
            f"**Processed BY: {credit}** \n\n"
            f"**╾───• Txtx Extractor •───╼** uploader in cheap price @king_rajasthan_23_bot"
        )
    except Exception as e:
        await safe_edit_message(editable, f"Error preparing caption: {e}", client)
        await input_msg.delete()
        for path in [input_file_path, json_file_path, html_file_path]:
            if os.path.exists(path):
                os.remove(path)
        return

    # Send HTML file
    try:
        await safe_send_document(m.chat.id, html_file_path, caption, client)
    except Exception as e:
        await safe_edit_message(editable, f"Error sending HTML file: {e}", client)
        await input_msg.delete()
        for path in [input_file_path, json_file_path, html_file_path]:
            if os.path.exists(path):
                os.remove(path)
        return

    # Send failed.txt if non-empty
    if failed_links:
        try:
            with open(failed_file_path, 'w', encoding='utf-8') as failed_file:
                for link in failed_links:
                    failed_file.write(link + "\n")
            await safe_send_document(m.chat.id, failed_file_path, "Failed links during processing.", client)
        except Exception as e:
            await safe_edit_message(editable, f"Error sending failed links file: {e}", client)
            await input_msg.delete()
            for path in [input_file_path, json_file_path, html_file_path, failed_file_path]:
                if os.path.exists(path):
                    os.remove(path)
            return

    # Send summary message
    try:
        summary_message = (
            f"Input links - Total: {input_link_counts['total']}, "
            f".mp4: {input_link_counts['.mp4']}, .pdf: {input_link_counts['.pdf']}, "
            f".ws: {input_link_counts['.ws']}, .m3u8: {input_link_counts['.m3u8']}\n"
            f"Output links - Total: {output_link_counts['total']}, "
            f".mp4: {output_link_counts['.mp4']}, .pdf: {output_link_counts['.pdf']}, "
            f".ws: {output_link_counts['.ws']}, .m3u8: {output_link_counts['.m3u8']}"
        )
        await safe_send_message(m.chat.id, summary_message, client)
    except Exception as e:
        await safe_edit_message(editable, f"Error sending summary: {e}", client)
        await input_msg.delete()
        for path in [input_file_path, json_file_path, html_file_path, failed_file_path]:
            if os.path.exists(path):
                os.remove(path)
        return

    # Clean up files
    for path in [input_file_path, json_file_path, html_file_path, failed_file_path]:
        if os.path.exists(path):
            os.remove(path)

    await input_msg.delete()
    await safe_edit_message(editable, "**Processing completed successfully!**", client)
