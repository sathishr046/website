from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import re
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"]}})

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                # Extract text with better handling of whitespace
                page_text = page.extract_text()
                # Normalize whitespace
                page_text = ' '.join(page_text.split())
                text += page_text + "\n"
            
            # Clean up the text
            text = text.replace('\x00', '')  # Remove null bytes
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            text = text.strip()
            return text
    except Exception as e:
        raise Exception(f"Error reading PDF: {str(e)}")

def analyze_receipt(text):
    try:
        # Initialize result dictionary
        result = {
            'student_details': {
                'name': None,
                'usn': None,
                'branch': None,
                'father_name': None,
                'receipt_no': None
            },
            'fees': [],
            'total_amount': 0,
            'transport_fee_found': False,
            'warnings': [],
            'errors': []
        }

        # Clean up the text first
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('Closure: ()=>String from Function toString..', '')

        # Extract receipt number and date
        receipt_match = re.search(r'Receipt No\s*:\s*(NCET/\d+/\d+-\d+)', text, re.IGNORECASE)
        if receipt_match:
            result['student_details']['receipt_no'] = receipt_match.group(1).strip()

        # Extract USN (Adm No)
        usn_match = re.search(r'Adm No\s*:\s*(\w+)', text, re.IGNORECASE)
        if usn_match:
            result['student_details']['usn'] = usn_match.group(1).strip()

        # Extract name
        name_match = re.search(r'Name\s*:\s*([^C]+?)(?=\s+Class|$)', text, re.IGNORECASE)
        if name_match:
            result['student_details']['name'] = name_match.group(1).strip()

        # Extract branch/class
        branch_match = re.search(r'Class/sec\s*:([^F]+?)(?=\s+Father|$)', text, re.IGNORECASE)
        if branch_match:
            result['student_details']['branch'] = branch_match.group(1).strip()

        # Extract father's name
        father_match = re.search(r"Father(?:'s)?\s*Name\s*:\s*([^D]+?)(?=\s+DType|$)", text, re.IGNORECASE)
        if father_match:
            result['student_details']['father_name'] = father_match.group(1).strip()

        # Extract fees - looking for transport fees specifically
        transport_match = re.search(r'Transport Fees\s+IInstallment\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if transport_match:
            result['transport_fee_found'] = True
            concession, amount = transport_match.groups()
            fee_entry = {
                'sno': '1',
                'particular': 'Transport Fees',
                'concession': float(concession),
                'amount': float(amount)
            }
            result['fees'].append(fee_entry)
            result['total_amount'] = float(amount)

        # Add warnings if needed
        if not result['transport_fee_found']:
            result['warnings'].append("Transport fee not found in the receipt")

        return result
    except Exception as e:
        raise Exception(f"Error analyzing receipt: {str(e)}")

@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                file.save(file_path)
                text = extract_text_from_pdf(file_path)
                analysis_result = analyze_receipt(text)
                
                return jsonify(analysis_result)
            except Exception as e:
                return jsonify({'error': str(e)}), 500
            finally:
                # Clean up the uploaded file
                if os.path.exists(file_path):
                    os.remove(file_path)
        
        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        return jsonify({'error': f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
