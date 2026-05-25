GET_STATE_QUERY = """
fragment CheckboxQuestion on Submission_CheckboxQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  checkboxResponse: response {
    chosen
    __typename
  }
  __typename
}
fragment CheckboxReflectQuestion on Submission_CheckboxReflectQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  checkboxReflectResponse: response {
    chosen
    __typename
  }
  __typename
}
fragment CodeExpressionQuestion on Submission_CodeExpressionQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    codeLanguage
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    replEvaluatorId
    starterCode {
      code
      __typename
    }
    __typename
  }
  codeExpressionResponse: response {
    answer {
      code
      __typename
    }
    __typename
  }
  __typename
}
fragment FileUploadQuestion on Submission_FileUploadQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    allowedFiles
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  fileUploadResponse: response {
    caption
    fileUrl
    title
    __typename
  }
  __typename
}
fragment MathQuestion on Submission_MathQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  mathResponse: response {
    answer
    __typename
  }
  __typename
}
fragment MultipleChoiceQuestion on Submission_MultipleChoiceQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  multipleChoiceResponse: response {
    chosen
    __typename
  }
  __typename
}
fragment MultipleChoiceReflectQuestion on Submission_MultipleChoiceReflectQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  multipleChoiceReflectResponse: response {
    chosen
    __typename
  }
  __typename
}
fragment MultipleChoiceFillableBlank on Submission_MultipleChoiceFillableBlank {
  fillableBlankId: id
  answerOptions {
    ...Option
    __typename
  }
  __typename
}
fragment MultipleChoiceFillableBlankResponse on Submission_MultipleChoiceFillableBlankResponse {
  responseId: id
  optionId
  __typename
}
fragment MultipleFillableBlanksResponse on Submission_MultipleFillableBlanksQuestionResponse {
  responses {
    ...MultipleChoiceFillableBlankResponse
    __typename
  }
  __typename
}
fragment MultipleFillableBlanksQuestion on Submission_MultipleFillableBlanksQuestion {
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    fillableBlanks {
      ...MultipleChoiceFillableBlank
      __typename
    }
    __typename
  }
  multipleFillableBlanksResponse: response {
    ...MultipleFillableBlanksResponse
    __typename
  }
  gradeSettings {
    maxScore
    __typename
  }
  __typename
}
fragment NumericQuestion on Submission_NumericQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  numericResponse: response {
    answer
    __typename
  }
  __typename
}
fragment OffPlatformQuestion on Submission_OffPlatformQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  __typename
}
fragment PlainTextQuestion on Submission_PlainTextQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  plainTextResponse: response {
    plainText
    __typename
  }
  __typename
}
fragment RegexQuestion on Submission_RegexQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  regexResponse: response {
    answer
    __typename
  }
  __typename
}
fragment RichTextQuestion on Submission_RichTextQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  richTextResponse: response {
    richText {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  __typename
}
fragment TextExactMatchQuestion on Submission_TextExactMatchQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  textExactMatchResponse: response {
    answer
    __typename
  }
  __typename
}
fragment TextReflectQuestion on Submission_TextReflectQuestion {
  gradeSettings {
    maxScore
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  textReflectResponse: response {
    answer
    __typename
  }
  __typename
}
fragment UrlQuestion on Submission_UrlQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  urlResponse: response {
    caption
    title
    url
    __typename
  }
  __typename
}
fragment WidgetQuestion on Submission_WidgetQuestion {
  gradeSettings {
    maxScore
    graderType
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    widgetSessionId
    __typename
  }
  widgetResponse: response {
    answer
    __typename
  }
  __typename
}
fragment SubmissionPart on Submission_SubmissionPart {
  ...CheckboxQuestion
  ...CheckboxReflectQuestion
  ...CodeExpressionQuestion
  ...FileUploadQuestion
  ...MathQuestion
  ...MultipleChoiceQuestion
  ...MultipleChoiceReflectQuestion
  ...MultipleFillableBlanksQuestion
  ...NumericQuestion
  ...OffPlatformQuestion
  ...PlainTextQuestion
  ...RegexQuestion
  ...RichTextQuestion
  ...TextBlock
  ...TextExactMatchQuestion
  ...TextReflectQuestion
  ...UrlQuestion
  ...WidgetQuestion
  __typename
}
fragment Submission on Submission_Submission {
  id
  parts {
    ...SubmissionPart
    __typename
  }
  instructions {
    ...SubmissionInstructions
    __typename
  }
  lastSavedAt
  __typename
}
fragment InProgressAttempt on Submission_InProgressAttempt {
  id
  allowedDuration
  draft {
    ...Submission
    __typename
  }
  autoSubmissionRequired
  remainingDuration
  startedTime
  submissionsAllowed
  submissionsMade
  submissionsRemaining
  __typename
}
fragment LastSubmission on Submission_LastSubmission {
  id
  submission {
    ...Submission
    __typename
  }
  submittedAt
  __typename
}
fragment NextAttempt on Submission_NextAttempt {
  allowedDuration
  submissionsAllowed
  __typename
}
fragment SubmissionRateLimiterConfig on Submission_RateLimiterConfig {
  attemptsRemainingIncreasesAt
  maxPerInterval
  timeIntervalDuration
  __typename
}
fragment Attempts on Submission_Attempts {
  lastSubmission {
    ...LastSubmission
    __typename
  }
  nextAttempt {
    ...NextAttempt
    __typename
  }
  attemptsAllowed
  attemptsMade
  attemptsRemaining
  inProgressAttempt {
    ...InProgressAttempt
    __typename
  }
  rateLimiterConfig {
    ...SubmissionRateLimiterConfig
    __typename
  }
  __typename
}
fragment AssignmentOutcome on Submission_AssignmentOutcome {
  earnedGrade
  gradeOverride {
    original
    override
    __typename
  }
  isPassed
  latePenaltyRatio
  __typename
}
fragment IntegrityAutoProctorSettings on Integrity_AutoProctorSettings {
  enabled
  clientId
  hashedAttemptId
  __typename
}
fragment IntegrityHonorlockSettings on Integrity_HonorlockSettings {
  enabled
  __typename
}
fragment IntegrityLockingBrowserSettings on Integrity_LockingBrowserSettings {
  enabled
  enabledForCurrentUser
  __typename
}
fragment IntegrityCourseraProctoringSettings on Integrity_CourseraProctoringSettings {
  enabled
  configuration {
    primaryCameraConfig {
      cameraStatus
      recordingStatus
      monitoringStatus
      __typename
    }
    secondaryCameraConfig {
      cameraStatus
      recordingStatus
      monitoringStatus
      __typename
    }
    __typename
  }
  __typename
}
fragment IntegrityVivaExamSettings on Integrity_VivaExamSettings {
  status
  __typename
}
fragment IntegritySession on Session_Session {
  id
  isPrivate
  __typename
}
fragment AcademicIntegritySettings on Integrity_IntegritySettings {
  attemptId
  session {
    ...IntegritySession
    __typename
  }
  honorlockSettings {
    ...IntegrityHonorlockSettings
    __typename
  }
  lockingBrowserSettings {
    ...IntegrityLockingBrowserSettings
    __typename
  }
  autoProctorSettings {
    ...IntegrityAutoProctorSettings
    __typename
  }
  courseraProctoringSettings {
    ...IntegrityCourseraProctoringSettings
    __typename
  }
  vivaExamSettings {
    ...IntegrityVivaExamSettings
    __typename
  }
  __typename
}
fragment Assignment on Submission_Assignment {
  id
  passingFraction
  assignmentType
  assignmentGradingType
  gradeSelectionStrategy
  requiredMobileFeatures
  learnerFeedbackVisibility
  __typename
}
fragment SlackIntegrationMetadata on Submission_SlackIntegrationMetadata {
  slackGroupId
  slackTeamId
  slackTeamDomain
  __typename
}
fragment SlackProfile on Submission_SlackProfile {
  slackTeamId
  slackUserId
  slackName
  deletedOrInactive
  __typename
}
fragment UserProfile on Submission_UserProfile {
  id
  email
  fullName
  photoUrl
  slackProfile {
    ...SlackProfile
    __typename
  }
  __typename
}
fragment TeamSubmitter on Submission_TeamSubmitter {
  id
  name
  teamActivityDescription
  slackIntegrationMetadata {
    ...SlackIntegrationMetadata
    __typename
  }
  memberProfiles {
    ...UserProfile
    __typename
  }
  __typename
}
fragment IndividualSubmitter on Submission_IndividualSubmitter {
  id
  __typename
}
fragment QueryStateSuccess on Submission_SubmissionState {
  allowedAction
  assignment {
    ...Assignment
    __typename
  }
  integritySettings {
    ...AcademicIntegritySettings
    __typename
  }
  submitter {
    ...IndividualSubmitter
    ...TeamSubmitter
    __typename
  }
  attempts {
    ...Attempts
    __typename
  }
  feedback {
    feedbackId: id
    outcome {
      ...OverallOutcome
      __typename
    }
    __typename
  }
  outcome {
    ...AssignmentOutcome
    __typename
  }
  manualGradingStatus
  warnings
  __typename
}
query QueryState($courseId: ID!, $itemId: ID!) {
  SubmissionState {
    queryState(courseId: $courseId, itemId: $itemId) {
      ... on Submission_QueryStateFailure {
        ...QueryStateFailure
        __typename
      }
      ... on Submission_SubmissionState {
        ...QueryStateSuccess
        __typename
      }
      __typename
    }
    __typename
  }
}
fragment OverallOutcome on Submission_OverallOutcome {
  latestScore
  highestScore
  maxScore
  __typename
}
fragment SubmissionInstructions on Submission_Instructions {
  overview {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  reviewCriteria {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  __typename
}
fragment QueryStateFailure on Submission_QueryStateFailure {
  errors {
    ...SubmissionInvalidAttemptIdError
    ...SubmissionInvalidHonorlockSessionError
    ...SubmissionNoAttemptInProgressError
    ...SubmissionNoOpenDraftError
    ...SubmissionQueryState_IpNotAllowedError
    ...SubmissionQueryState_TeamNotAssignedError
    ...SubmissionReworkSubmission_NoSubmissionToReworkError
    ...SubmissionSaveResponses_InvalidResponsesError
    ...SubmissionStaffGradingStartedError
    ...SubmissionStartAttempt_OutOfAttemptsError
    __typename
  }
  __typename
}
fragment SubmissionInvalidAttemptIdError on Submission_InvalidAttemptIdError {
  errorCode
  __typename
}
fragment SubmissionInvalidHonorlockSessionError on Submission_InvalidHonorlockSessionError {
  errorCode
  __typename
}
fragment SubmissionNoAttemptInProgressError on Submission_NoAttemptInProgressError {
  errorCode
  __typename
}
fragment SubmissionNoOpenDraftError on Submission_NoOpenDraftError {
  errorCode
  __typename
}
fragment SubmissionQueryState_IpNotAllowedError on Submission_QueryState_IPNotAllowedError {
  errorCode
  __typename
}
fragment SubmissionQueryState_TeamNotAssignedError on Submission_QueryState_TeamNotAssignedError {
  errorCode
  __typename
}
fragment SubmissionReworkSubmission_NoSubmissionToReworkError on Submission_ReworkSubmission_NoSubmissionToReworkError {
  errorCode
  __typename
}
fragment SubmissionSaveResponses_InvalidResponsesError on Submission_SaveResponses_InvalidResponsesError {
  errorCode
  __typename
}
fragment SubmissionStaffGradingStartedError on Submission_StaffGradingStartedError {
  errorCode
  __typename
}
fragment SubmissionStartAttempt_OutOfAttemptsError on Submission_StartAttempt_OutOfAttemptsError {
  errorCode
  __typename
}
fragment SubmissionCmlContent on CmlContent {
  cmlValue
  dtdId
  htmlWithMetadata {
    html
    metadata {
      hasAssetBlock
      hasCodeBlock
      hasMath
      isPlainText
      __typename
    }
    __typename
  }
  __typename
}
fragment SubmissionHtmlContent on Submission_HtmlContent {
  value
  __typename
}
fragment Option on Submission_MultipleChoiceOption {
  display {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  optionId: id
  __typename
}
fragment TextBlock on Submission_TextBlock {
  partId: id
  title
  body {
    ...SubmissionCmlContent
    __typename
  }
  __typename
}
"""

SAVE_RESPONSES_QUERY = """
mutation Submission_SaveResponses($input: Submission_SaveResponsesInput!) {
  Submission_SaveResponses(input: $input) {
    ... on Submission_SaveResponsesSuccess {
      __typename
      submissionState {
        allowedAction
        warnings
        attempts {
          inProgressAttempt {
            draft {
              id
              lastSavedAt
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
    }
    ... on Submission_SaveResponsesFailure {
      __typename
      errors {
        errorCode
        __typename
      }
    }
    __typename
  }
}
"""

SUBMIT_DRAFT_QUERY = """
mutation Submission_SubmitLatestDraft(
  $input: Submission_SubmitLatestDraftInput!
) {
  Submission_SubmitLatestDraft(input: $input) {
    ... on Submission_SubmitLatestDraftSuccess {
      __typename
      submissionState {
        allowedAction
        warnings
        __typename
      }
    }
    ... on Submission_SubmitLatestDraftFailure {
      __typename
      errors {
        errorCode
        __typename
      }
    }
    __typename
  }
}
"""

INITIATE_ATTEMPT_QUERY = """
mutation Submission_StartAttempt($courseId: ID!, $itemId: ID!) {
  Submission_StartAttempt(input: {courseId: $courseId, itemId: $itemId}) {
    ... on Submission_StartAttemptSuccess {
      submissionState {
        assignment {
          id
          __typename
        }
        __typename
      }
      __typename
    }
    ... on Submission_StartAttemptFailure {
      errors {
        errorCode
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

ASSIGNMENT_FEEDBACK_QUERY = """
fragment FullFeedback on Submission_Feedback {
  assignmentLevelRubrics {
    ...RubricFeedback
    __typename
  }
  feedbackId: id
  outcome {
    ...OverallOutcome
    __typename
  }
  parts {
    ...FeedbackPart
    __typename
  }
  instructions {
    ...SubmissionInstructions
    __typename
  }
  __typename
}

query AssignmentFeedback($courseId: ID!, $itemId: ID!) {
  SubmissionState {
    queryState(courseId: $courseId, itemId: $itemId) {
      ... on Submission_QueryStateFailure {
        ...QueryStateFailure
        __typename
      }
      ... on Submission_SubmissionState {
        feedback {
          ...FullFeedback
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment OverallOutcome on Submission_OverallOutcome {
  latestScore
  highestScore
  maxScore
  __typename
}

fragment SubmissionInstructions on Submission_Instructions {
  overview {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  reviewCriteria {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  __typename
}

fragment QueryStateFailure on Submission_QueryStateFailure {
  errors {
    ...SubmissionInvalidAttemptIdError
    ...SubmissionInvalidHonorlockSessionError
    ...SubmissionNoAttemptInProgressError
    ...SubmissionNoOpenDraftError
    ...SubmissionQueryState_IpNotAllowedError
    ...SubmissionQueryState_TeamNotAssignedError
    ...SubmissionReworkSubmission_NoSubmissionToReworkError
    ...SubmissionSaveResponses_InvalidResponsesError
    ...SubmissionStaffGradingStartedError
    ...SubmissionStartAttempt_OutOfAttemptsError
    __typename
  }
  __typename
}

fragment SubmissionInvalidAttemptIdError on Submission_InvalidAttemptIdError {
  errorCode
  __typename
}

fragment SubmissionInvalidHonorlockSessionError on Submission_InvalidHonorlockSessionError {
  errorCode
  __typename
}

fragment SubmissionNoAttemptInProgressError on Submission_NoAttemptInProgressError {
  errorCode
  __typename
}

fragment SubmissionNoOpenDraftError on Submission_NoOpenDraftError {
  errorCode
  __typename
}

fragment SubmissionQueryState_IpNotAllowedError on Submission_QueryState_IPNotAllowedError {
  errorCode
  __typename
}

fragment SubmissionQueryState_TeamNotAssignedError on Submission_QueryState_TeamNotAssignedError {
  errorCode
  __typename
}

fragment SubmissionReworkSubmission_NoSubmissionToReworkError on Submission_ReworkSubmission_NoSubmissionToReworkError {
  errorCode
  __typename
}

fragment SubmissionSaveResponses_InvalidResponsesError on Submission_SaveResponses_InvalidResponsesError {
  errorCode
  __typename
}

fragment SubmissionStaffGradingStartedError on Submission_StaffGradingStartedError {
  errorCode
  __typename
}

fragment SubmissionStartAttempt_OutOfAttemptsError on Submission_StartAttempt_OutOfAttemptsError {
  errorCode
  __typename
}

fragment SubmissionCmlContent on CmlContent {
  cmlValue
  dtdId
  htmlWithMetadata {
    html
    metadata {
      hasAssetBlock
      hasCodeBlock
      hasMath
      isPlainText
      __typename
    }
    __typename
  }
  __typename
}

fragment SubmissionHtmlContent on Submission_HtmlContent {
  value
  __typename
}

fragment Option on Submission_MultipleChoiceOption {
  display {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  optionId: id
  __typename
}

fragment TextBlock on Submission_TextBlock {
  partId: id
  title
  body {
    ...SubmissionCmlContent
    __typename
  }
  __typename
}

fragment BoxViewDocumentAnnotationRubricFeedback on Submission_BoxViewDocumentAnnotationRubricFeedback {
  fileId
  id
  reviewResponseId
  prompt {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  __typename
}

fragment MultilineRubricFeedback on Submission_MultilineRubricFeedback {
  aiSuggestionId
  id
  input
  maxScore
  prompt {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  score
  richTextInput {
    ...SubmissionCmlContent
    __typename
  }
  graderType
  __typename
}

fragment RubricOption on Submission_RubricOption {
  display {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  optionId: id
  points
  selected
  __typename
}

fragment OptionsRubricFeedback on Submission_OptionsRubricFeedback {
  aiSuggestionId
  id
  options {
    ...RubricOption
    __typename
  }
  richTextInput {
    ...SubmissionCmlContent
    __typename
  }
  prompt {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  graderType
  __typename
}

fragment GradedOption on Submission_GradedOption {
  correctlyAnswered
  display {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  optionId: id
  feedback {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  __typename
}

fragment QuestionOutcome on Submission_QuestionOutcome {
  score
  maxScore
  __typename
}

fragment AutoGradedFeedback on Submission_AutoGradedFeedback {
  correctness
  feedback {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  autoGradedFeedbackOutcome: outcome {
    ...QuestionOutcome
    __typename
  }
  __typename
}

fragment ManuallyGradedFeedback on Submission_ManuallyGradedFeedback {
  manuallyGradedFeedbackOutcome: outcome {
    ...QuestionOutcome
    __typename
  }
  rubrics {
    ...RubricFeedback
    __typename
  }
  graderType
  __typename
}

fragment GradedCheckboxQuestion on Submission_GradedCheckboxQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...GradedOption
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  checkboxResponse: response {
    chosen
    __typename
  }
  __typename
}

fragment GradedCheckboxReflectQuestion on Submission_GradedCheckboxReflectQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...GradedOption
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  checkboxReflectResponse: response {
    chosen
    __typename
  }
  __typename
}

fragment GradedCodeExpressionQuestion on Submission_GradedCodeExpressionQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    codeLanguage
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    replEvaluatorId
    starterCode {
      code
      __typename
    }
    __typename
  }
  codeExpressionResponse: response {
    answer {
      code
      __typename
    }
    __typename
  }
  __typename
}

fragment GradedFileUploadQuestion on Submission_GradedFileUploadQuestion {
  feedback {
    ...ManuallyGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    allowedFiles
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  fileUploadResponse: response {
    caption
    fileUrl
    title
    __typename
  }
  __typename
}

fragment GradedMathQuestion on Submission_GradedMathQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    correctAnswer {
      id
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  mathResponse: response {
    answer
    __typename
  }
  __typename
}

fragment GradedMultipleChoiceQuestion on Submission_GradedMultipleChoiceQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  multipleChoiceResponse: response {
    chosen
    __typename
  }
  __typename
}

fragment GradedMultipleChoiceReflectQuestion on Submission_GradedMultipleChoiceReflectQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    options {
      ...Option
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  multipleChoiceReflectResponse: response {
    chosen
    __typename
  }
  __typename
}

fragment GradedMultipleChoiceFillableBlank on Submission_GradedMultipleChoiceFillableBlank {
  fillableBlankId: id
  isCorrect
  answerOptions {
    ...Option
    __typename
  }
  feedback {
    ...SubmissionCmlContent
    ...SubmissionHtmlContent
    __typename
  }
  __typename
}

fragment GradedMultipleFillableBlanksQuestion on Submission_GradedMultipleFillableBlanksQuestion {
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    fillableBlanks {
      ...GradedMultipleChoiceFillableBlank
      __typename
    }
    __typename
  }
  multipleFillableBlanksResponse: response {
    responses {
      ... on Submission_MultipleChoiceFillableBlankResponse {
        responseId: id
        optionId
        __typename
      }
      __typename
    }
    __typename
  }
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  __typename
}

fragment GradedNumericQuestion on Submission_GradedNumericQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  numericResponse: response {
    answer
    __typename
  }
  __typename
}

fragment GradedOffPlatformQuestion on Submission_GradedOffPlatformQuestion {
  feedback {
    ...ManuallyGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  __typename
}

fragment GradedPlainTextQuestion on Submission_GradedPlainTextQuestion {
  feedback {
    ...ManuallyGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  plainTextResponse: response {
    plainText
    __typename
  }
  __typename
}

fragment GradedRegexQuestion on Submission_GradedRegexQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  regexResponse: response {
    answer
    __typename
  }
  __typename
}

fragment GradedRichTextQuestion on Submission_GradedRichTextQuestion {
  feedback {
    ...ManuallyGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  richTextResponse: response {
    richText {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  __typename
}

fragment GradedTextExactMatchQuestion on Submission_GradedTextExactMatchQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    correctAnswers {
      answer
      id
      __typename
    }
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  textExactMatchResponse: response {
    answer
    __typename
  }
  __typename
}

fragment GradedTextReflectQuestion on Submission_GradedTextReflectQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  textReflectResponse: response {
    answer
    __typename
  }
  __typename
}

fragment GradedUrlQuestion on Submission_GradedUrlQuestion {
  feedback {
    ...ManuallyGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    plagiarismCheckStatus
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    __typename
  }
  urlResponse: response {
    caption
    title
    url
    __typename
  }
  __typename
}

fragment GradedWidgetQuestion on Submission_GradedWidgetQuestion {
  feedback {
    ...AutoGradedFeedback
    __typename
  }
  partId: id
  questionSchema {
    prompt {
      ...SubmissionCmlContent
      ...SubmissionHtmlContent
      __typename
    }
    widgetSessionId
    __typename
  }
  widgetResponse: response {
    answer
    __typename
  }
  __typename
}

fragment RubricFeedback on Submission_RubricFeedback {
  ...BoxViewDocumentAnnotationRubricFeedback
  ...MultilineRubricFeedback
  ...OptionsRubricFeedback
  __typename
}

fragment FeedbackPart on Submission_FeedbackPart {
  ...GradedCheckboxQuestion
  ...GradedCheckboxReflectQuestion
  ...GradedCodeExpressionQuestion
  ...GradedFileUploadQuestion
  ...GradedMathQuestion
  ...GradedMultipleChoiceQuestion
  ...GradedMultipleChoiceReflectQuestion
  ...GradedMultipleFillableBlanksQuestion
  ...GradedNumericQuestion
  ...GradedOffPlatformQuestion
  ...GradedPlainTextQuestion
  ...GradedRegexQuestion
  ...GradedRichTextQuestion
  ...GradedTextExactMatchQuestion
  ...GradedTextReflectQuestion
  ...GradedUrlQuestion
  ...GradedWidgetQuestion
  ...TextBlock
  __typename
}
"""
