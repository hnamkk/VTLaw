import { expect, test, type Page } from '@playwright/test';

type ChatSessionSummary = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_bookmarked: boolean;
  bookmark_title: string | null;
  bookmarked_at: string | null;
};

type ChatMessagesResponse = {
  session: ChatSessionSummary;
  messages: Array<{
    message_id: string;
    role: 'user' | 'assistant';
    content: string;
    citations: [];
    faithfulness_score: number | null;
    is_out_of_scope: boolean;
    created_at: string;
    answer_mode?: string;
    clarification_question?: string | null;
  }>;
};

const SESSION_ID = '20020020-0200-2002-0020-020020020055';
const USER_ID = '10010010-0100-1001-0010-010010010055';
const SESSION_TITLE = 'Làm rõ xử phạt';
const QUESTION = 'Thế còn trường hợp này thì sao?';
const CLARIFICATION_TEXT =
  'Bạn vui lòng nêu rõ hành vi, loại xe hoặc văn bản cần tra cứu để tôi xác định đúng căn cứ.';

const sessionSummary: ChatSessionSummary = {
  session_id: SESSION_ID,
  title: SESSION_TITLE,
  created_at: '2026-07-09T01:00:00Z',
  updated_at: '2026-07-09T01:05:00Z',
  is_bookmarked: false,
  bookmark_title: null,
  bookmarked_at: null,
};

async function navigateToView(page: Page, viewId: string) {
  await expect.poll(async () => {
    return page.evaluate(() => document.querySelector('.view-section.active')?.id || null);
  }).not.toBeNull();
  await page.evaluate((targetView) => {
    window.dispatchEvent(new CustomEvent('app:navigate', { detail: targetView }));
  }, viewId);
  await expect.poll(async () => {
    return page.evaluate(() => document.querySelector('.view-section.active')?.id || null);
  }).toBe(viewId);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    ({ userId }) => {
      window.localStorage.setItem(
        'legalai_auth',
        JSON.stringify({
          access_token: 'test-access-token',
          token_type: 'bearer',
          user: {
            user_id: userId,
            email: 'clarification@example.test',
            username: 'clarification-user',
            role: 'USER',
            is_active: true,
          },
        }),
      );
    },
    { userId: USER_ID },
  );
});

test('chat clarification survives stream render and history reload', async ({ page }) => {
  test.skip(
    test.info().project.name === 'mobile',
    'Regression này khóa flow history clarification trên layout desktop.',
  );

  let streamRequestBody: { question?: string; session_id?: string } | null = null;
  let messageRequestCount = 0;

  await page.route(/\/api\/v1\/chat\/sessions(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [sessionSummary] }),
    });
  });

  await page.route(/\/api\/v1\/chat\/sessions\/[^/]+\/messages$/, async (route) => {
    messageRequestCount += 1;
    const response: ChatMessagesResponse =
      messageRequestCount === 1
        ? {
            session: sessionSummary,
            messages: [],
          }
        : {
            session: sessionSummary,
            messages: [
              {
                message_id: 'message-user-1',
                role: 'user',
                content: QUESTION,
                citations: [],
                faithfulness_score: null,
                is_out_of_scope: false,
                created_at: '2026-07-09T01:06:00Z',
              },
              {
                message_id: 'message-assistant-1',
                role: 'assistant',
                content: CLARIFICATION_TEXT,
                citations: [],
                faithfulness_score: null,
                is_out_of_scope: false,
                created_at: '2026-07-09T01:06:10Z',
                answer_mode: 'clarification_needed',
                clarification_question: CLARIFICATION_TEXT,
              },
            ],
          };

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });

  await page.route('**/api/v1/chat/stream', async (route) => {
    streamRequestBody = route.request().postDataJSON() as {
      question?: string;
      session_id?: string;
    };
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `data: ${JSON.stringify({
        type: 'done',
        trace_id: 'trace-clarification-1',
        session_id: SESSION_ID,
        content: CLARIFICATION_TEXT,
        citations: [],
        provision_citations: [],
        document_sources: [],
        historical_references: [],
        clarification_question: CLARIFICATION_TEXT,
        answer_mode: 'clarification_needed',
        risk_level: 'medium',
        confidence: { level: 'low', reason: 'query_clarification' },
        faithfulness_score: null,
        is_out_of_scope: false,
        reranker_failed: false,
        reranker_used: false,
        reranker_error_code: null,
        low_confidence: false,
        retrieval_candidate_count: 0,
        rerank_top_score: null,
        query_intent: 'general_legal',
        guardrail_triggered: true,
        guardrail_stage: 'input',
        guardrail_reason: 'query_clarification',
      })}\n\n`,
    });
  });

  await page.goto('/');
  await navigateToView(page, 'view-chat');

  const chatView = page.locator('#view-chat');
  const infoPanel = chatView.locator('.chat-info-panel');
  const historyItem = chatView.locator('.chat-history-item').filter({ hasText: SESSION_TITLE }).first();
  await expect(historyItem).toBeVisible();

  await historyItem.getByRole('button').first().click();
  await expect(chatView.getByText('Xin chào bạn!')).toBeVisible();

  await page.locator('#fullChatInput').fill(QUESTION);
  await page.locator('#fullSendChatBtn').click();

  await expect(chatView.locator('.message-wrapper.bot').last().getByText(CLARIFICATION_TEXT)).toBeVisible();
  await expect(infoPanel.getByText('Cần làm rõ trước khi tra cứu')).toBeVisible();
  await expect(infoPanel.getByText(CLARIFICATION_TEXT)).toBeVisible();
  await expect.poll(() => streamRequestBody?.question ?? null).toBe(QUESTION);
  await expect.poll(() => streamRequestBody?.session_id ?? null).toBe(SESSION_ID);

  await chatView.getByRole('button', { name: 'Tạo cuộc trò chuyện mới' }).click();
  await expect(chatView.getByText(CLARIFICATION_TEXT)).toHaveCount(0);

  await historyItem.getByRole('button').first().click();

  await expect(chatView.getByText(QUESTION)).toBeVisible();
  await expect(chatView.locator('.message-wrapper.bot').last().getByText(CLARIFICATION_TEXT)).toBeVisible();
  await expect(infoPanel.getByText('Cần làm rõ trước khi tra cứu')).toBeVisible();
  await expect(infoPanel.getByText(CLARIFICATION_TEXT)).toBeVisible();
  expect(messageRequestCount).toBe(2);
});
