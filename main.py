from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from typing import List,Dict
import requests
import base64
import pymongo
import pandas as pd
from io import BytesIO
from fastapi.encoders import jsonable_encoder
import google.generativeai as genai
from dotenv import load_dotenv
import os, json, re
import smtplib
from email.message import EmailMessage
from getpass import getpass
app = FastAPI()
origins = [
        "https://prostack-2skvc96j7-yagnesh-reddys-projects.vercel.app",
    "http://localhost:3000"  
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
genai.configure(api_key = os.getenv("API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# mycli = pymongo.MongoClient("mongodb://localhost:27017/")
mycli = pymongo.MongoClient("mongodb+srv://codeexam2025:fMSLwZlYVzown45h@demo.0ycgeuo.mongodb.net/?retryWrites=true&w=majority&appName=demo")
mydb = mycli["codingEditor"]
mycol_email = mydb["Emails"]
mycol_que = mydb["quesions"]
mycol_choiceque = mydb["choices"]


class EmailPassword(BaseModel):
    email: str
    password: str
@app.post("/app/email")
async def email(data: EmailPassword):
    # global email 
    email = data.email 
    password = data.password
    if (data.password.isdigit()):
        password = int(data.password)
        check = mycol_email.find_one({"email":email,"password":password,'Attempt':'Not Attempt'})
        check_2 = mycol_email.find_one({"email":email,"password":password})
        if check:
           return "sucss"
        elif check_2:
           return "User Already Write this exam."
        else:
           return "User Email/Password incorrect"
    else:
           return "User Email/Password incorrect"


class QueNos(BaseModel):
    queNo : str
    user : str

@app.post("/app/questions")
async def quesions(data : QueNos):
    # print("quesion number >> 2")
    que = mycol_que.find_one({"questionNo":data.queNo})
    first_input = que["inputs"][0]["input"] if que.get("inputs") else ""
    # print(first_input,".............................")
    li = [{"a": i} for i in range(1, 11)]
    fetch_marks = mycol_email.find_one({"email": data.user}, {'_id': 0})
    QAtt = "NotYet"
    try:
        qmarks = fetch_marks['QMarks'][0]
    except:
        qmarks = []
    return {
        "title": que.get("title"),
        "question": que.get("description"),
        "first_input": first_input,
        "testcases": li,
        "QAtt" : qmarks
    }


class users(BaseModel):
    user : str


@app.post("/app/user")
async def user(data:users):

    check = mycol_email.find_one({"email":data.user,'Attempt':'Not Attempt'})
    NoOfQue = list(mycol_que.find({},{"_id":0}))
    LastQueNoobj =  list(mycol_que.find({}, {'_id': 0}).sort('_id', -1).limit(1))
    LastChoiceQueNoobj =  list(mycol_choiceque.find({}, {'_id': 0}).sort('_id', -1).limit(1))
    LastQueNo = LastQueNoobj[0]['questionNo']
    Choice_total = LastChoiceQueNoobj[0]['QNO']
    if NoOfQue and check:
       return {"TotalQue":NoOfQue,"Choice_total":Choice_total,"lastQuesionNo":LastQueNo}
    else:
        return "err"
# Judge0 API details
JUDGE0_URL = "https://judge0-ce.p.rapidapi.com/submissions"
HEADERS = {
    "X-RapidAPI-Key": "640db5e88bmsh0e7bf6495c90995p1cad09jsn5cec7c140fdf",
    "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
    "Content-Type": "application/json"
}




# Request schema
class CodeData(BaseModel):
    code: str
    input: str = ""
    language_id: int

@app.post("/app/get_data")
async def get_data(data: CodeData):
    payload = {
        "language_id": data.language_id,
        "source_code": data.code,
        "stdin": data.input
    }

    response = requests.post(
        JUDGE0_URL + "?base64_encoded=false&wait=true",
        headers=HEADERS,
        json=payload
    )
    
    result = response.json()
    output = result.get("stdout") or result.get("stderr") or result.get("compile_output") or "No output or execution failed."
    return {"output": output}

class TestData(BaseModel):
      code: str
      language_id: int
      queNo:str
      user:str
@app.post("/app/subinput")
def subinput(data : TestData):
    code = data.code
    question = mycol_que.find_one({"questionNo": data.queNo})
    results = []
    count = 0
    db_marks =  mycol_email.find_one({"email":data.user},{"_id":0})
    # print(">>>>>>>>>>marks",data.user,">>>>>>",user_marks)
    que_marks = db_marks['marks']
    for case in question["inputs"]:
        count += 1
        # try:
        #     _ = list(map(int, case["input"].split()))
        # except ValueError:
        #     return {"error": f"Invalid input format in test case {case['test']}: {case['input']}"}
        payload = {
           "language_id": data.language_id,
           "source_code": code,
           "stdin": case["input"]
        } 

# Send to Judge0
        response = requests.post(
            JUDGE0_URL + "?base64_encoded=false&wait=true",
            headers=HEADERS,
            json=payload
        )
        # resp_data = response.json()
        result = response.json()
    # Decode outputs
      
        output = result.get("stdout", "").strip() if result.get("stdout") else ""
        passed = output == case["output"]
        if passed:
            que_marks += case["marks"]
        results.append({
          "input": case["input"],
          "stdout": output,
          "expetedout":case["output"],
          "passed": passed,
          "test":count
         })
    fetch_marks = mycol_email.find_one({"email":data.user},{'_id':0})
    que_marks_list = fetch_marks.get('QMarks',[])
    if data.queNo in fetch_marks['QMarks'][0].keys():
        if fetch_marks['QMarks'][0][data.queNo] < que_marks:
            que_marks_list[0][data.queNo]=que_marks
            mycol_email.update_one({"email":data.user},{'$set':{"QMarks":que_marks_list}})
    else:
        que_marks_list[0][data.queNo]=que_marks
        mycol_email.update_one({"email":data.user},{'$set':{"QMarks":que_marks_list}})
    return results

@app.post("/app/admin")
async def admin(file: UploadFile = File(...)):
    # Read the uploaded Excel file
    contents = await file.read()
    excel_data = BytesIO(contents)
    # Convert bytes to pandas DataFrame
    df = pd.read_csv(excel_data)
    df["marks"] = 0
    df["choiceMarks"] = 0
    df["TotalMarks"] = 0
    df["Attempt"] = "Not Attempt"
    df["QMarks"] =  [[{}] for _ in range(len(df))]
    Excel_data = df.to_dict(orient='records')
    
    # print(dff)
    Mongo_data = mycol_email.find({},{"_id":0})
    if Mongo_data:
        Mongo_list = [rec["email"] for rec in Mongo_data]
        result = 0
        duplicates = 0
        for data in Excel_data:
            if data["email"] not in Mongo_list:
                mycol_email.insert_one(data)
                result += 1
            else:
                duplicates += 1
    else:
        duplicates = 0
        mycol_email.insert_many(Excel_data)
        result = len(Excel_data)
    total = len(list(mycol_email.find({},{"_id":0})))
    return {"AddData":result,"TotalData":total,"Duplicates":duplicates}

@app.get("/app/dele")
def dele():
    mycol_email.delete_many({})
    return "delete sucess"
@app.get('/app/datashow')
def datashow():
    data = mycol_email.find({},{"_id":0})
    result = []
    for item in data:
        result.append(item)
    return result
class names(BaseModel):
    name :str
@app.post('/app/search')
def search(data:names):
    print(data.name)
    data = mycol_email.find({ "name": { "$regex": data.name, "$options": "i" } },{'_id':0})
    result = []
    for item in data:
        result.append(item)
    return result
class sub(BaseModel):
    user:str
@app.post('/app/submit')
def submit(data:sub):
    # print(data.user)
    Coding_marks = 0
    mongo_user_data = mycol_email.find_one({'email':data.user},{'_id':0})
    user_marks = mongo_user_data.get('QMarks',[])
    for _,v in user_marks[0].items():
        Coding_marks += v
    Choice_marks = mongo_user_data.get("choiceMarks", 0)
    total_marks = Choice_marks + Coding_marks
    mycol_email.update_one({'email':data.user},{'$set':{'marks':Coding_marks,"TotalMarks":total_marks,'Attempt':'Attempted'}})
    return {"State":"sucess","Choice_marks":Choice_marks,"Coding_marks":Coding_marks,"total_marks":total_marks}

@app.post('/app/uploadQuestions')
async def uploadQuesion(file:UploadFile = File(...)):
    print("submit data ....................")
    contents = await file.read()
    excel_data = BytesIO(contents)
    # Convert bytes to pandas DataFrame
    df = pd.read_csv(excel_data)
    print(df)
    data = df.to_dict(orient="records")
    mycol_que.insert_many(data)
    return {"data": data}

@app.get('/app/new')
def getQues():
    que = mycol_que.find({},{'_id':0})
    result = []
    for i in que:
        result.append(i)
    return result

class QNo(BaseModel):
    Qno: str
@app.post('/app/QueDel')
def DelQue(data:QNo):
    que = list(mycol_que.find({}, {'_id': 0}).sort('questionNo', -1).limit(1))
    if not que:
        return {'status': 'no questions available'}

    CurrentQueNo = que[0]['questionNo']

    # Delete the question
    mycol_que.delete_one({'questionNo': data.Qno})

    if CurrentQueNo == data.Qno:
        return {'status': 'success'}
    else:
        for i in range(int(data.Qno), int(CurrentQueNo)):
            mycol_que.update_one(
                {'questionNo': str(i + 1)},
                {"$set": {'questionNo': str(i)}},
                upsert=False
            )
        return {'status': 'success'}

class QuesionType(BaseModel):
    Qname: str
@app.post('/app/Ai')
def showQue(data:QuesionType):

    que = list(mycol_que.find({},{'_id':0}).sort({'_id': -1}).limit(1))


    def_que = """{
  "questionNo": "0",
  "title": "String Pattern Matching",
  "description": "Given a string `s` and a pattern `p`, implement pattern matching with support for '.' and '*' where:\\n\\n'.' Matches any single character.\\n'*' Matches zero or more of the preceding element.\\n\\nThe matching should cover the entire input string (not partial).\\n\\n**Input:**\\n- The first line contains the string `s`.\\n- The second line contains the pattern `p`.\\n\\n**Output:**\\n- A single line containing `true` if the pattern matches the string, and `false` otherwise.\\n\\n**Constraints:**\\n- 1 <= length of `s` <= 20\\n- 1 <= length of `p` <= 30\\n- `s` contains only lowercase English letters.\\n- `p` contains only lowercase English letters, '.', and '*'.\\n- It is guaranteed for each appearance of the character '*', there will be a previous valid character to match.\\n\\n**Explanation:**\\nThe problem requires implementing a pattern matching algorithm that supports the wildcard characters '.' and '*'. The '.' character can match any single character, and the '*' character can match zero or more occurrences of the character that precedes it. The function should return true if the pattern matches the entire input string, and false otherwise.\\n\\n**Example:**\\n- Input:\\n  `aa`\\n  `a`\\n- Output:\\n  `false`\\n- Explanation: Because 'a' does not match the entire string 'aa'.\\n\\n- Input:\\n  `aa`\\n  `a*`\\n- Output:\\n  `true`\\n- Explanation: '*' means zero or more of the preceding element, 'a'. Therefore, by repeating 'a' once, it becomes 'aa'.\\n\\n- Input:\\n  `ab`\\n  `.*`\\n- Output:\\n  `true`\\n- Explanation: '.*' means 'zero or more (*) of any character (.)'.\\n",
  "inputs": [
    {
      "test": "1",
      "input": "aa\\na",
      "output": "false",
      "marks": 10
    },
    {
      "test": "2",
      "input": "aa\\na*",
      "output": "true",
      "marks": 10
    },
    {
      "test": "3",
      "input": "ab\\n.*",
      "output": "true",
      "marks": 10
    },
    {
      "test": "4",
      "input": "aab\\nc*a*b",
      "output": "true",
      "marks": 10
    },
    {
      "test": "5",
      "input": "mississippi\\nmis*is*p*.",
      "output": "false",
      "marks": 10
    },
    {
      "test": "6",
      "input": "abc\\nabc",
      "output": "true",
      "marks": 10
    },
    {
      "test": "7",
      "input": "abcd\\nab.*d",
      "output": "true",
      "marks": 10
    },
    {
      "test": "8",
      "input": "abbbbcd\\nab*cd",
      "output": "true",
      "marks": 10
    },
    {
      "test": "9",
      "input": "xyz\\nxy.",
      "output": "true",
      "marks": 10
    },
    {
      "test": "10",
      "input": "a\\na.",
      "output": "false",
      "marks": 10
    }
  ]
}"""


    if que:
        Quesion = que[0]
    else:
        Quesion = json.loads(def_que)

    Quesion_data =f"""I have a coding compiler for a coding quiz. This is the format of JSON data: {json.dumps(Quesion)}.  
This is my last question in the compiler — read this and give me exactly in this format.  

Include the following:
- `questionNo` (Next Quesion number to generate.)
- `title` (you can improve the title based on the question content)
- `description`: This must be a well-formatted string including input format, output format, constraints, explanation, and an example — just like how it is written on LeetCode or HackerRank.  
  (Do **not** create separate keys for input/output/constraints/explanation — write them all inside the `description` as plain text.)

For test cases:
- There should be exactly 10 test cases.
- Each test case must contain `test`, `input`, `output`, and `marks`.
- Total marks are 100, so each test case should get **10 marks**.
- Keep all key names and format **exactly the same** — do not add any new keys or change any names.

The question title is: `{data.Qname}` — if needed, improve it slightly to make it clear and relevant.

Only return **pure JSON data** — nothing else. No text, no explanation. I want to insert it directly into my MongoDB collection.
"""

    
   
    result = model.start_chat().send_message(Quesion_data).text
    cleaned_result = re.sub(r"```json|```", "", result).strip()
    json_result = json.loads(cleaned_result)
    # print(json_result)

    mycol_que.insert_one(json_result)
    return {"states":"sucess"}

@app.get("/app/sortAllQue")
def sortAllQue():
    questions = list(mycol_que.find().sort("_id", 1))
    for index, q in enumerate(questions):
        mycol_que.update_one({"_id": q["_id"]}, {"$set": {"questionNo": str(index + 1)}})
    return {"states":"sucess"}
@app.get("/app/DeleteAllQue")
def DeleteAllQue():
     mycol_que.delete_many({},{})
     return {"states":"sucess"}
class Forget(BaseModel):
    email : str
@app.post('/app/forgetPassword')
def forgetpassword(data : Forget):
    database_user = mycol_email.find_one({"email":data.email},{'_id':0})
    if database_user :
         receiver_email = data.email
         user_password = database_user["password"]
         username = database_user["name"]
   
         # Email configuration
         sender_email = "codeexam2025@gmail.com"
         subject = "ProStack Academy - Password Recovery"
    
           # Create the email message
         msg = EmailMessage()
         msg['Subject'] = subject
         msg['From'] = sender_email
         msg['To'] = receiver_email

          # HTML content with improved security warning
         html_content = f"""
          <!DOCTYPE html>
          <html>
          <head>
              <meta charset="UTF-8">
             <title>{subject}</title>
                <style>
                    body {{
                     font-family: 'Arial', sans-serif;
                     line-height: 1.6;
                     color: #333;
                     max-width: 600px;
                     margin: 0 auto;
                     padding: 20px;
                     background-color: #f9f9f9;
                 }}
                 .container {{
                     background: #fff;
                     border-radius: 8px;
                     padding: 25px;
                     box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                 }}
                 .header {{
                     color: #2c3e50;
                     text-align: center;
                     border-bottom: 2px solid #3498db;
                     padding-bottom: 10px;
                     margin-bottom: 20px;
                 }}
                 .info-box {{
                     background: #f1f9fe;
                     border-left: 4px solid #3498db;
                        padding: 15px;
                     margin: 20px 0;
                     border-radius: 0 4px 4px 0;
                 }}
                 .credentials {{
                     font-size: 16px;
                     margin: 5px 0;
                     word-break: break-all;
                 }}
                 .warning {{
                     color: #e74c3c;
                     font-weight: bold;
                     background: #fff3f3;
                     padding: 10px;
                     border-radius: 4px;
                     border-left: 4px solid #e74c3c;
                 }}
                 .footer {{
                     text-align: center;
                     margin-top: 25px;
                     font-size: 12px;
                     color: #7f8c8d;
                 }}
             </style>
         </head>
         <body>
             <div class="container">
                  <div class="header">
                      <h1>ProStack Academy</h1>
                      <h2>Password Recovery</h2>
                  </div>

                  <p>Hello {username},</p>
                  <p>We received a request to retrieve your account credentials. Below are your login details:</p>

                    <div class="info-box">
                     <p class="credentials"><strong>Username:</strong> {username}</p>
                        <p class="credentials"><strong>Password:</strong> {user_password}</p>
                  </div>

                   <div class="footer">
                      <p>© 2025 ProStack Academy. All rights reserved.</p>
                  </div>
              </div>
          </body>
        </html>
          """

          # Attach HTML content
         msg.add_alternative(html_content, subtype='html')

         # Send the email with error handling
         try:
             with smtplib.SMTP("smtp.gmail.com", 587) as server:
                  server.starttls()
                 # Use getpass for more secure password input
                  password = "wqep gphf zmgc ymob"
                  server.login(sender_email, password)
                  server.send_message(msg)
             return {"states": "Password recovery email sent successfully!","flag":"true"}
         except Exception as e:
              return {"states":  f"Failed to send email: {str(e)}","flag":"false"}
    else:
        return {"states": f"{data.email} Email Doesn't Exist in database","flag":"false"}
    

@app.get('/app/choicesQues')
def choiceQues():
    choices_Ques = mycol_choiceque.find({},{'_id':0})
    li = []
    for Each_que in choices_Ques:
        li.append(Each_que)
    return {"states":"true","response":li}

class choiceResult(BaseModel):
    Result : int
    user : str
@app.post('/app/choicesResults')
def choiceResults(data : choiceResult):
    mycol_email.update_one({"email":data.user},{"$set":{"choiceMarks":data.Result}})
    return {"states":"sucess"}
@app.get('/app/demo')
def demo():

   mycol_demo = mydb["demo"]
   data = mycol_demo.find({},{"_id":0})
   res = []
   for i in data:
       res.append(i)
#    print(res[0]['info'])
   return {"response":res[0]['info']}

@app.get('/app/MCQData')
def getQues():
    que = mycol_choiceque.find({},{'_id':0})
    result = []
    for i in que:
        result.append(i)
    return result
@app.get("/app/DeleteAllMCQsQue")
def DeleteAllQue():
     mycol_choiceque.delete_many({},{})
     return {"states":"sucess"}
@app.get("/app/sortAllMCQsQue")
def sortAllQue():
    questions = list(mycol_choiceque.find().sort("_id", 1))
    for index, q in enumerate(questions):
        mycol_choiceque.update_one({"_id": q["_id"]}, {"$set": {"QNO": index + 1}})
    return {"states":"sucess"}
class QuesionType(BaseModel):
    Qname: str

@app.post('/app/MCQsAi')
def showQue(data: QuesionType):
    Quesion_data = f"""
I have a MCQ for a quiz. Give the output exactly in the following JSON format:

For each question:
- `QNO`: The next question number to generate.
- `Question`: Improve the clarity and relevance of the question title if needed.
- `choices`: Exactly 4 multiple choice options.
- If the question type is `"radio"`:
    - Only one correct answer should be given as a string under `"Ans"`.
- If the question type is `"checkbox"`:
    - One or more correct answers should be given as a list of strings under `"Ans"`.

Static values:
- `"type"`: I will specify `"radio"` or `"checkbox"`.
- `"flag"`: Always `"false"`.
- `"marks"`: Always `1`.

Only return **pure JSON data** — no explanation, no markdown, no extra text. I want to insert it directly into my MongoDB collection.

🔹 Example for `"radio"`:
{{
  "QNO": 0,
  "Question": "Select the correct output for print(\\"hi\\"*2)",
  "choices": [
    "hihi",
    "Error",
    "hi2",
    "hi hi"
  ],
  "type": "radio",
  "Ans": "hihi",
  "flag": "false",
  "marks": 1
}}

🔹 Example for `"checkbox"`:
{{
  "QNO": 0,
  "Question": "What does the expression 3**2 return in Python?",
  "choices": [
    "6",
    "9",
    "8",
    "Error"
  ],
  "type": "checkbox",
  "Ans": ["9"],
  "flag": "false",
  "marks": 1
}}

The question title is: {data.Qname} — improve it slightly if needed to make it clear and relevant.
"""

    # Get response from model
    raw_result = model.start_chat().send_message(Quesion_data).text

    # Clean markdown if exists
    cleaned_result = re.sub(r"```json|```", "", raw_result).strip()

    try:
        json_result = json.loads(cleaned_result)
    except json.JSONDecodeError:
        return {"status": "failed", "reason": "Invalid JSON response from model", "raw": raw_result}

    # Insert to MongoDB
    mycol_choiceque.insert_one(json_result)

    return {"status": "sucess"}
class QNo(BaseModel):
    Qno: int
@app.post('/app/MCQsQueDel')
def DelQue(data:QNo):
    que = list(mycol_choiceque.find({}, {'_id': 0}).sort('QNO', -1).limit(1))
    if not que:
        return {'status': 'no questions available'}

    CurrentQueNo = que[0]['QNO']

    # Delete the question
    mycol_choiceque.delete_one({'QNO': data.Qno})

    if CurrentQueNo == data.Qno:
        return {'status': 'success'}
    else:
        for i in range(int(data.Qno), int(CurrentQueNo)):
            mycol_choiceque.update_one(
                {'QNO': i + 1},
                {"$set": {'QNO': i}},
                upsert=False
            )
        return {'status': 'success'}
