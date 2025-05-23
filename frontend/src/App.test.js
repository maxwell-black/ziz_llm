import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';

// Mock the fetch function
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ answer: 'Mocked bot response' }),
  })
);

beforeEach(() => {
  // Clear all previous mock calls before each test
  fetch.mockClear();
});

test('renders App and main components', () => {
  render(<App />);
  // Check for header text (using text match as h1 might not have a specific role)
  expect(screen.getByText(/Ž/i)).toBeInTheDocument(); // Header title
  
  // Check for input placeholder
  expect(screen.getByPlaceholderText(/.../i)).toBeInTheDocument(); // Input field
  
  // Check for Send button
  expect(screen.getByRole('button', { name: /Send/i })).toBeInTheDocument(); // Send button
  
  // Check for the help toggle button
  expect(screen.getByTestId('toggle-help-button')).toBeInTheDocument();
});

test('lazy loads HelpSection when "Show Help" button is clicked', async () => {
  render(<App />);

  // Ensure HelpSection is not visible initially
  expect(screen.queryByTestId('help-section-loaded')).not.toBeInTheDocument();

  // Find and click the "Show Help" button
  const showHelpButton = screen.getByTestId('toggle-help-button');
  expect(showHelpButton).toHaveTextContent('Show Help'); // Initial button text
  fireEvent.click(showHelpButton);

  // Check for loading fallback
  expect(screen.getByTestId('help-section-loading')).toBeInTheDocument();

  // Wait for HelpSection to load and check for its content
  // Using findByTestId which combines waitFor and getByTestId
  const helpSection = await screen.findByTestId('help-section-loaded');
  expect(helpSection).toBeInTheDocument();
  expect(screen.getByText(/Help & FAQs/i)).toBeInTheDocument(); // Check for heading in HelpSection

  // Check that the button text has changed
  expect(showHelpButton).toHaveTextContent('Hide Help');

  // Optional: Test hiding the section
  fireEvent.click(showHelpButton);
  expect(screen.queryByTestId('help-section-loaded')).not.toBeInTheDocument();
  expect(showHelpButton).toHaveTextContent('Show Help'); // Button text back to Show Help
});

test('sending a message and receiving a response', async () => {
  render(<App />);
  const inputElement = screen.getByPlaceholderText(/.../i);
  const sendButton = screen.getByRole('button', { name: /Send/i });

  // Type a message and send
  fireEvent.change(inputElement, { target: { value: 'Hello bot' } });
  fireEvent.click(sendButton);

  // Check if user message appears
  expect(await screen.findByText(/Hello bot/)).toBeInTheDocument();
  
  // Check if fetch was called correctly
  expect(fetch).toHaveBeenCalledWith('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: 'Hello bot' }),
  });

  // Check for loading indicator for bot message
  // The actual loading dots are multiple spans, so we check for the container
  expect(screen.getByText((content, element) => element.classList.contains('loading') && element.classList.contains('bot'))).toBeInTheDocument();


  // Wait for bot response
  const botResponse = await screen.findByText(/Mocked bot response/);
  expect(botResponse).toBeInTheDocument();

  // Ensure loading indicator is gone
  expect(screen.queryByText((content, element) => element.classList.contains('loading') && element.classList.contains('bot'))).not.toBeInTheDocument();
});
