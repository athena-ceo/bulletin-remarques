# TODO: Future Features and Enhancements

This file tracks potential features and enhancements for future development of the bulletin generation application.

## 🎯 Suggested New Features

### 1. Batch Export
**Priority:** Medium  
**Description:** Add ability to export evaluations for all classes at once in a single file or ZIP archive.

**Implementation Ideas:**
- Add "Export All" button in UI
- Generate combined PDF or ZIP file with all class results
- Include metadata (date, model used, etc.)

---

### 2. Evaluation Templates
**Priority:** Medium  
**Description:** Allow users to customize evaluation guidelines and prompt templates.

**Implementation Ideas:**
- Create UI for editing prompt templates
- Save custom templates for reuse
- Include several pre-made templates for different teaching styles
- Template variables for grade thresholds, style preferences

---

### 3. History Tracking
**Priority:** Low  
**Description:** Keep track of previous evaluation generations with timestamps and configurations.

**Implementation Ideas:**
- SQLite database for history
- View/compare past evaluations for same students
- Track which configurations produce best results
- Export history as CSV or JSON

---

### 4. Comparison Mode
**Priority:** Low  
**Description:** Compare student performance across different concours blancs visually.

**Implementation Ideas:**
- Add charts/graphs showing progression over CB1, CB2, CB3
- Highlight improvements or regressions
- Generate trend analysis
- Export comparison reports

---

### 5. Draft Saving
**Priority:** Medium  
**Description:** Save work in progress and resume later without losing data.

**Implementation Ideas:**
- Auto-save to local storage or session file
- "Save Draft" and "Load Draft" buttons
- Store partially completed evaluations
- Warning before closing with unsaved work

---

### 6. Multi-language Support
**Priority:** Low  
**Description:** Support generating evaluations in languages other than French.

**Implementation Ideas:**
- Language selector in UI
- Translate prompts and UI elements
- Support for Spanish, German, etc. teachers
- Maintain same pedagogical approach across languages

---

### 7. Bulk Student Management
**Priority:** Medium  
**Description:** Edit, filter, and manage student data before generating evaluations.

**Implementation Ideas:**
- Filter students by average grade, attendance, etc.
- Bulk edit student information
- Mark students to skip
- Preview data before generation

---

### 8. Evaluation Quality Metrics
**Priority:** Low  
**Description:** Analyze and rate the quality of generated evaluations.

**Implementation Ideas:**
- Length statistics
- Readability scores
- Keyword analysis
- Flag potentially problematic evaluations for review

---

### 9. Integration with School Software
**Priority:** High  
**Description:** Direct integration with common French school management systems (Pronote, etc.).

**Implementation Ideas:**
- Export in formats compatible with Pronote, Éclat, etc.
- API integration for direct upload
- Automatic student data import
- Sync grades and evaluations

---

### 10. Collaborative Features
**Priority:** Low  
**Description:** Allow multiple teachers to collaborate and share templates/results.

**Implementation Ideas:**
- Shared workspace for department
- Template library
- Peer review of evaluations
- Comments and suggestions

---

### 11. Mobile App
**Priority:** Low  
**Description:** Mobile version for reviewing and editing evaluations on the go.

**Implementation Ideas:**
- Responsive design optimization
- Native mobile app (iOS/Android)
- Offline mode
- Voice input for editing

---

### 12. AI Model Comparison
**Priority:** Medium  
**Description:** Compare outputs from different AI models side-by-side.

**Implementation Ideas:**
- Generate same evaluation with multiple models
- Display all versions for comparison
- Vote on best version
- Track which models work best for different cases

---

## 📝 Notes

- Priorities are subject to change based on user feedback
- Each feature should maintain backward compatibility
- Consider performance impact before implementation
- All features should follow existing code standards and type hints

## 🔄 Status Tracking

- [ ] Not started
- [x] Completed
- [⏸] On hold
- [🚧] In progress

To implement a feature, create a new branch and reference this TODO file in your PR.

