import sys
import os

# --- Add project root to Python path for direct script execution ---
_current_script_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_script_dir, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# --- End of sys.path modification ---

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import joblib
import logging
import nltk 
from nltk.corpus import stopwords 
import re 

logger = logging.getLogger(__name__)
# Configure logging for this script if it's run directly
if __name__ == "__main__": 
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Preprocessing Logic (Inlined - Keep Identical in validator.py) ---
def _get_english_stopwords():
    """Ensures stopwords are downloaded and returns the set."""
    try:
        sw = set(stopwords.words('english'))
    except LookupError: 
        try:
            nltk.data.find('corpora/stopwords.zip') 
        except nltk.downloader.DownloadError: 
            logger.warning("[TRAINER] NLTK stopwords package not found. Attempting download of 'stopwords' package.")
            nltk.download('stopwords', quiet=True)
        except Exception as e: 
            logger.error(f"[TRAINER] NLTK data path issue for stopwords: {e}. Ensure NLTK data is correctly installed/accessible.")
            raise 
        sw = set(stopwords.words('english')) 
    return sw

ENGLISH_STOPWORDS_SET = _get_english_stopwords()

def common_preprocess_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    
    text = text.lower()
    # Keep alphanumeric, spaces, and potentially useful symbols for tech content
    text = re.sub(r'[^\w\s\.\(\)\+\-\*/\=\<\>\%]', '', text) 
    # Numbers are KEPT by default in this version. 
    # To remove numbers, uncomment the next line and test its impact:
    # text = re.sub(r'\d+', ' <NUM_TOKEN> ', text) # Replace numbers with a token, add spaces around token
    # text = re.sub(r'\s+', ' ', text).strip() # Clean up extra spaces if using <NUM_TOKEN>
    
    words = text.split()
    # Remove stopwords. Allow single characters as they might be part of technical terms now.
    processed_words = [w for w in words if w not in ENGLISH_STOPWORDS_SET and len(w) > 0]
            
    return " ".join(processed_words)
# --- End of Inlined Preprocessing Logic ---


def train_help_post_model(config_model_version: str = "1.0.0"):
    logger.info("="*40); logger.info(" Starting help_post model training ".center(40, "=")); logger.info("="*40)
    data_file_path = os.path.join(PROJECT_ROOT, 'data', 'help_post_training_data.csv')
    model_output_dir = os.path.join(PROJECT_ROOT, 'data', 'trained_models'); os.makedirs(model_output_dir, exist_ok=True)
    model_filename = f'help_post_classifier_v{config_model_version}.pkl'; model_full_path = os.path.join(model_output_dir, model_filename)

    logger.info(f"Loading training data from: {data_file_path}")
    if not os.path.exists(data_file_path): logger.error(f"Training data file not found at {data_file_path}"); return
    try: df = pd.read_csv(data_file_path)
    except Exception as e: logger.error(f"Failed to read CSV '{data_file_path}': {e}"); return
        
    logger.info(f"Initial training data shape: {df.shape}")
    if not ({'label', 'content'}.issubset(df.columns)): logger.error("'label' or 'content' column missing."); return

    df['label'] = pd.to_numeric(df['label'], errors='coerce'); df.dropna(subset=['label'], inplace=True)
    df['label'] = df['label'].astype(int); df = df[df['label'].isin([0, 1])]
    df['content'] = df['content'].astype(str).fillna('')
    
    logger.info(f"Shape after label cleaning & content fillna: {df.shape}")
    if df.shape[0] < 20: logger.error(f"Not enough valid data points (need >= 20). Found: {df.shape[0]}"); return
    logger.info(f"Label distribution after cleaning:\n{df['label'].value_counts(normalize=True)}")

    logger.info("Preprocessing text data using INLINED common_preprocess_text...")
    df['processed_content'] = df['content'].apply(common_preprocess_text)
    if (df['processed_content'].str.strip() == '').sum() > 0: logger.warning(f"{(df['processed_content'].str.strip() == '').sum()} entries became empty after processing.")

    X = df['processed_content']; y = df['label']
    if len(X) < 4: logger.error(f"Not enough data to train (need >= 4). Found: {len(X)}"); return

    test_size = 0.25 if len(X) >= 10 else (0.1 if len(X) >= 4 else 0)
    stratify_y = None
    if y.nunique() >= 2 and test_size > 0:
        counts = y.value_counts()
        if all(counts * test_size >= 1): stratify_y = y # Check if each class has at least 1 sample in test
        else: logger.warning(f"Cannot stratify effectively. Counts: {counts.to_dict()}")

    if test_size == 0: X_train, y_train, X_test, y_test = X, y, pd.Series(dtype='object', index=pd.Index([])), pd.Series(dtype='int', index=pd.Index([]))
    else: X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42, stratify=stratify_y)

    logger.info(f"Sizes: Train={len(X_train)}, Test={len(X_test)}")
    if len(y_train) > 0: logger.info(f"Train Labels:\n{y_train.value_counts(normalize=True, dropna=False)}")
    if len(y_test) > 0: logger.info(f"Test Labels:\n{y_test.value_counts(normalize=True, dropna=False)}")

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2, max_df=0.95, stop_words=None)), # min_df=2, max_df=0.95 are good defaults
        ('clf', LogisticRegression(solver='liblinear', random_state=42, class_weight='balanced', C=2.0))]) # C=2.0 for less regularization

    logger.info("Training model..."); pipeline.fit(X_train, y_train)

    if len(X_test) > 0 and len(y_test) > 0 and y_test.nunique() > 0: # Ensure test set is usable
        logger.info("Evaluating on test set..."); y_pred = pipeline.predict(X_test)
        logger.info(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
        logger.info("Confusion Matrix:\n" + str(confusion_matrix(y_test, y_pred)))
        clf_classes = list(pipeline.named_steps['clf'].classes_)
        target_names = [f'Class {c}' for c in clf_classes]
        if sorted(clf_classes) == [0,1]: target_names = [('Class 0 (Bad)' if c==0 else 'Class 1 (Good)') for c in clf_classes]
        logger.info("Classification Report:\n" + classification_report(y_test, y_pred, target_names=target_names, zero_division=0))
        try:
            coefs = pipeline.named_steps['clf'].coef_[0]
            feats = pipeline.named_steps['tfidf'].get_feature_names_out()
            coef_df = pd.DataFrame({'feature': feats, 'coefficient': coefs}).sort_values(by='coefficient', ascending=False)
            logger.info("Top Positive Features:\n" + str(coef_df.head(20)))
            logger.info("Top Negative Features:\n" + str(coef_df.tail(20).sort_values(by='coefficient')))
        except Exception as e: logger.warning(f"Coef display error: {e}")
        if not X_test[y_test == 1].empty: logger.info(f"Sample GOOD (processed): '{X_test[y_test == 1].iloc[0][:100]}...' -> Probs: {pipeline.predict_proba([X_test[y_test == 1].iloc[0]])[0]}")
        if not X_test[y_test == 0].empty: logger.info(f"Sample BAD (processed): '{X_test[y_test == 0].iloc[0][:100]}...' -> Probs: {pipeline.predict_proba([X_test[y_test == 0].iloc[0]])[0]}")
    else: logger.warning("Test set empty or unusable for full evaluation.")

    logger.info(f"Saving model to: {model_full_path}"); joblib.dump(pipeline, model_full_path)
    logger.info("SUCCESS: Model training complete."); logger.info("="*40)

if __name__ == "__main__":
    train_help_post_model(config_model_version="1.0.0")