import { getErrorMessageFromResponse } from './errorUtils';

describe('getErrorMessageFromResponse', () => {
  it('should extract error message from valid JSON response', async () => {
    const mockResponse = {
      status: 400,
      json: jest.fn().mockResolvedValue({ error: 'Bad Request Error' })
    };
    const result = await getErrorMessageFromResponse(mockResponse);
    expect(result).toBe('Bad Request Error');
  });

  it('should fallback to status code if JSON does not contain error field', async () => {
    const mockResponse = {
      status: 404,
      json: jest.fn().mockResolvedValue({ someOtherField: 'Not Found' })
    };
    const result = await getErrorMessageFromResponse(mockResponse);
    expect(result).toBe('HTTP error! Status: 404');
  });

  it('should fallback to status code if JSON parsing fails', async () => {
    const mockResponse = {
      status: 500,
      json: jest.fn().mockRejectedValue(new Error('Invalid JSON'))
    };
    const result = await getErrorMessageFromResponse(mockResponse);
    expect(result).toBe('HTTP error! Status: 500');
  });
});
