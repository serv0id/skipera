
ASSIGNMENT_SUBMIT_QUERY = """
mutation GetPreSignedUrl($input: Submission_FileUploadQuestionGenerateUploadUrlInput!) {
  Submission_FileUploadQuestionGenerateUploadUrl(input: $input) {
    url
    additionalHeaders {
      name
      value
      __typename
    }
    __typename
  }
}

"""