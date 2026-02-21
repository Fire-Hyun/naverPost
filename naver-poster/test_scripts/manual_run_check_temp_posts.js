#!/usr/bin/env node

/**
 * 네이버 블로그 임시글함 확인 스크립트
 */

const path = require('path');
const fs = require('fs');
const { loadOrCreateSession } = require('../dist/naver/session');

async function checkTempPosts() {
    console.log('🔍 네이버 블로그 임시글함 확인 중...');

    try {
        const config = {
            blogId: process.env.NAVER_BLOG_ID ?? 'jun12310',
            userDataDir: './.secrets/naver_user_data_dir',
            headless: false  // 시각적으로 확인할 수 있도록
        };

        // 세션 생성
        const writeUrl = `https://blog.naver.com/${config.blogId}?Redirect=Write&`;
        const session = await loadOrCreateSession({
            userDataDir: config.userDataDir,
            headless: config.headless
        }, writeUrl);

        console.log('✅ 네이버 블로그 로그인 완료');

        // 임시글함으로 이동
        const tempPostsUrl = `https://blog.naver.com/${config.blogId}?Redirect=Temp&`;
        console.log(`📂 임시글함으로 이동: ${tempPostsUrl}`);

        await session.page.goto(tempPostsUrl, { waitUntil: 'networkidle', timeout: 30000 });

        // 페이지 로드 대기
        await new Promise(resolve => setTimeout(resolve, 3000));

        // 스크린샷 저장
        const screenshotPath = path.resolve(process.cwd(), 'artifacts', 'temp_posts_screenshot.png');
        await session.page.screenshot({
            path: screenshotPath,
            fullPage: true
        });
        console.log(`📷 스크린샷 저장: ${screenshotPath}`);

        // 임시글 목록 찾기 시도
        try {
            await session.page.waitForSelector('.temp_post_list, .post_list, .list_temp', { timeout: 10000 });

            const tempPosts = await session.page.evaluate(() => {
                const posts = [];
                // 다양한 선택자로 임시글 찾기
                const selectors = ['.temp_post_list li', '.post_list li', '.list_temp li',
                                 '[class*="temp"] [class*="title"]', '[class*="post"] [class*="title"]'];

                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        elements.forEach((el, index) => {
                            const title = el.textContent?.trim() || `Post ${index + 1}`;
                            posts.push(title);
                        });
                        break;
                    }
                }

                return posts;
            });

            if (tempPosts.length > 0) {
                console.log('📝 발견된 임시글들:');
                tempPosts.forEach((title, index) => {
                    console.log(`  ${index + 1}. ${title}`);
                });
            } else {
                console.log('📝 임시글이 없거나 찾을 수 없습니다.');
            }

        } catch (error) {
            console.log('⚠️ 임시글 목록을 찾는데 실패했지만 스크린샷으로 확인 가능합니다.');
        }

        // HTML 덤프 저장
        const htmlPath = path.resolve(process.cwd(), 'artifacts', 'temp_posts_page.html');
        const htmlContent = await session.page.content();
        fs.writeFileSync(htmlPath, htmlContent);
        console.log(`💾 HTML 저장: ${htmlPath}`);

        console.log('🎯 임시글함 확인 완료!');
        console.log('   스크린샷과 HTML 파일을 확인해주세요.');

        // 잠시 대기 (수동 확인 시간)
        console.log('⏱️ 10초 후 브라우저를 닫습니다...');
        await new Promise(resolve => setTimeout(resolve, 10000));

        await session.browser.close();

    } catch (error) {
        console.error('❌ 오류 발생:', error.message);
        process.exit(1);
    }
}

checkTempPosts();
