from pyrogram import Client, filters
from pyrogram.types import Message as m
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
import aiohttp
import asyncio
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor

# Import app from Extractor
from Extractor import app

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define THREADPOOL
THREADPOOL = ThreadPoolExecutor(max_workers=10)

# Define run_async
def run_async(func, *args):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(func(*args))
    loop.close()

# Placeholder functions
def find_appx_matching_apis(search_terms):
    logger.warning("find_appx_matching_apis not implemented. Please provide the function.")
    return []

async def fetch_appx_html_to_json(session, url, headers):
    logger.warning("fetch_appx_html_to_json not implemented. Replace with actual implementation.")
    return {}

async def process_folder_wise_course_0(session, api, batch_id, headers, user_id):
    logger.warning(f"process_folder_wise_course_0 not implemented for batch {batch_id}")
    return []

async def process_folder_wise_course_1(session, api, batch_id, headers, user_id):
    logger.warning(f"process_folder_wise_course_1 not implemented for batch {batch_id}")
    return []

# Command handler for /feappx
@app.on_message(filters.command("feappx"))
async def feappx_command(app, message: m):
    user_id = message.from_user.id
    THREADPOOL.submit(run_async, process_appxwp, app, message, user_id)

# Process Appxwp function
async def process_appxwp(app: Client, m: m, user_id: int):
    loop = asyncio.get_event_loop()
    CONNECTOR = aiohttp.TCPConnector(limit=100, loop=loop)

    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            editable = await m.reply_text("**Enter App Name Or Api**")

            try:
                input1 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                api = input1.text
                await input1.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return

            if not (api.startswith("http://") or api.startswith("https://")):
                api = api
                search_api = [term.strip() for term in api.split()]

                matches = find_appx_matching_apis(search_api)

                if matches:
                    text = ''
                    for cnt, item in enumerate(matches):
                        name = item['name']
                        api = item["api"]
                        text += f'{cnt + 1}. ```\n{name}:{api}```\n'
                        
                    await editable.edit(f"**Send index number of the Batch to download.\n\n{text}**")

                    try:
                        input2 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                        raw_text2 = input2.text
                        await input2.delete(True)
                    except:
                        await editable.edit("**Timeout! You took too long to respond**")
                        return
                
                    if input2.text.isdigit() and 1 <= int(input2.text) <= len(matches):
                        selected_api_index = int(input2.text.strip())
                        item = matches[selected_api_index - 1]
                        api = item['api']
                        selected_app_name = item['name']
                    else:
                        await editable.edit("**Error : Wrong Index Number**")
                        return
                else:
                    await editable.edit("**No matches found. Enter Correct App Starting Word**")
                    return
            else:
                api = "https://" + api.replace("https://", "").replace("http://", "").rstrip("/")
                selected_app_name = api

            token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6IjEwMTU1NTYyIiwiZW1haWwiOiJhbm9ueW1vdXNAZ21haWwuY29tIiwidGltZXN0YW1wIjoxNzQ1MDc5MzgyLCJ0ZW5hbnRUeXBlIjoidXNlciIsInRlbmFudE5hbWUiOiIiLCJ0ZW5hbnRJZCI6IiIsImRpc3Bvc2FibGUiOmZhbHNlfQ.EfwLhNtbzUVs1qRkMqc3P6ObkKSO0VYWKdAe6GmhdAg"
            userid = "10155562"
                
            headers = {
                'User-Agent': "okhttp/4.9.1",
                'Accept-Encoding': "gzip",
                'client-service': "Appx",
                'auth-key': "appxapi",
                'user_app_category': "",
                'language': "en",
                'device_type': "ANDROID"
            }
            
            res1 = await fetch_appx_html_to_json(session, f"{api}/get/courselist", headers)
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/courselistnewv2", headers)

            courses1 = res1.get("data", []) if res1 and res1.get('status') == 200 else []
            total1 = res1.get("total", 0) if res1 and res1.get('status') == 200 else 0

            courses2 = res2.get("data", []) if res2 and res2.get('status') == 200 else []
            total2 = res2.get("total", 0) if res2 and res2.get('status') == 200 else 0
            
            courses = courses1 + courses2
            total = total1 + total2

            if courses:
                if total > 50:
                    text = ''
                    for cnt, course in enumerate(courses):
                        name = course["course_name"]
                        price = course["price"]
                        text += f'{cnt + 1}. {name} 💵₹{price}\n'
                    
                    course_details = f"{user_id}_paid_course_details"
                
                    with open(f"{course_details}.txt", 'w') as f:
                        f.write(text)
                        
                    caption = f"**App Name : ```\n{selected_app_name}```\nBatch Name : ```\nPaid Course Details```**"
                                
                    files = [f"{course_details}.txt"]
                                
                    for file in files:
                        file_ext = os.path.splitext(file)[1][1:]
                        try:
                            with open(file, 'rb') as f:
                                await editable.delete(True)
                                doc = await m.reply_document(document=f, caption=caption, file_name=f"paid course details.{file_ext}")
                                editable = await m.reply_text("**Send index number From the course details txt File to download.**")
                        except FileNotFoundError:
                            logging.error(f"File not found: {file}")
                        except Exception as e:
                            logging.exception(f"Error sending document {file}:")
                        finally:
                            try:
                                os.remove(file)
                                logging.info(f"Removed File After Sending : {file}")
                            except OSError as e:
                                logging.error(f"Error deleting {file}: {e}")
                else:
                    text = ''
                    for cnt, course in enumerate(courses):
                        name = course["course_name"]
                        price = course["price"]
                        text += f'{cnt + 1}. ```\n{name} 💵₹{price}```\n'
                    await editable.edit(f"**Send index number of the course to download.\n\n{text}**")
            else:
                raise Exception("Did not found any course")
                
            try:
                input5 = await app.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                raw_text5 = input5.text
                await input5.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return
                
            if input5.text.isdigit() and 1 <= int(input5.text) <= len(courses):
                selected_course_index = int(input5.text.strip())
                course = courses[selected_course_index - 1]
                selected_batch_id = course['id']
                selected_batch_name = course['course_name']
                folder_wise_course = course.get("folder_wise_course", "")
                clean_batch_name = f"{selected_batch_name.replace('/', '-').replace('|', '-')[:min(244, len(selected_batch_name))]}"
                clean_file_name = f"{user_id}_{clean_batch_name}"
                
            else:
                raise Exception("Wrong Index Number")
        
            await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
            
            start_time = time.time()
            
            headers = {
                "Client-Service": "Appx",
                "Auth-Key": "appxapi",
                "source": "website",
                "Authorization": token,
                "User-ID": userid
            }

            all_outputs = []

            if folder_wise_course == 0:
                logging.info(f"User ID: {user_id} - Processing as non-folder-wise (folder_wise_course = 0)")
                all_outputs = await process_folder_wise_course_0(session, api, selected_batch_id, headers, user_id)

            elif folder_wise_course == 1:
                logging.info(f"User ID: {user_id} - Processing as folder-wise (folder_wise_course = 1)")
                all_outputs = await process_folder_wise_course_1(session, api, selected_batch_id, headers, user_id)

            else:
                logging.info(f"User ID: {user_id} - folder_wise_course is neither 0 nor 1.  Processing with both methods sequentially.")
                # Process as if folder_wise_course is 0
                logging.info(f"User ID: {user_id} - Processing as non-folder-wise (folder_wise_course = 0)")
                outputs_0 = await process_folder_wise_course_0(session, api, selected_batch_id, headers, user_id)
                all_outputs.extend(outputs_0)

                # Process as if folder_wise_course is 1
                logging.info(f"User ID: {user_id} - Processing as folder-wise (folder_wise_course = 1)")
                outputs_1 = await process_folder_wise_course_1(session, api, selected_batch_id, headers, user_id)
                all_outputs.extend(outputs_1)
            
            if all_outputs:
            
                with open(f"{clean_file_name}.txt", 'w') as f:
                    for output_line in all_outputs:
                        f.write(output_line)
                        
                end_time = time.time()
                response_time = end_time - start_time
                minutes = int(response_time // 60)
                seconds = int(response_time % 60)

                if minutes == 0:
                    if seconds < 1:
                        formatted_time = f"{response_time:.2f} seconds"
                    else:
                        formatted_time = f"{seconds} seconds"
                else:
                    formatted_time = f"{minutes} minutes {seconds} seconds"
                                    
                caption = f"**App Name : ```\n{selected_app_name}```\nBatch Name : ```\n{selected_batch_name}``````\nTime Taken : {formatted_time}```**"
                                
                files = [f"{clean_file_name}.txt"]
                for file in files:
                    file_ext = os.path.splitext(file)[1][1:]
                    try:
                        with open(file, 'rb') as f:
                            await editable.delete(True)
                            doc = await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.{file_ext}")
                    except FileNotFoundError:
                        logging.error(f"File not found: {file}")
                    except Exception as e:
                        logging.exception(f"Error sending document {file}:")
                    finally:
                        try:
                            os.remove(file)
                            logging.info(f"Removed File After Sending : {file}")
                        except OSError as e:
                            logging.error(f"Error deleting {file}: {e}")
            else:
                raise Exception("Didn't Found Any Content In The Course")
                
            
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            try:
                await editable.edit(f"**Error : {e}**")
            except Exception as ee:
                logging.error(f"Failed to send error message to user in callback: {ee}")
        finally:
            if session:
                await session.close()
            await CONNECTOR.close()
