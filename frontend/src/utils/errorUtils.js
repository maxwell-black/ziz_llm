export const getErrorMessageFromResponse = async (response) => {
  let errorMsg = `HTTP error! Status: ${response.status}`;
  try {
    const errData = await response.json();
    errorMsg = errData.error || errorMsg;
  } catch (e) {
    // Ignore if response body isn't valid JSON
  }
  return errorMsg;
};
