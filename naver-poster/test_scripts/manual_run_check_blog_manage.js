#!/usr/bin/env node

/**
 * 네이버 블로그 관리 페이지에서 임시글 확인
 */

const path = require('path');
const fs = require('fs');
const { loadOrCreateSession } = require('../dist/naver/session');

async function checkBlogManage() {
    console.log('🔍 네이버 블로그 관리 페이지 접속 중...');

    try {
        const config = {
            blogId: process.env.NAVER_BLOG_ID ?? 'jun12310',
            userDataDir: './.secrets/naver_user_data_dir',
            headless: false
        };

        // 세션 생성 (초기 URL은 일반 블로그)
        const writeUrl = `https://blog.naver.com/${config.blogId}`;
        const session = await loadOrCreateSession({
            userDataDir: config.userDataDir,
            headless: config.headless
        }, writeUrl);

        console.log('✅ 네이버 블로그 접속 완료');

        // 관리 페이지로 이동
        const manageUrl = `https://blog.naver.com/ManageList.naver?blogId=${config.blogId}`;
        console.log(`📊 관리 페이지로 이동: ${manageUrl}`);

        await session.page.goto(manageUrl, { waitUntil: 'networkidle', timeout: 30000 });
        await new Promise(resolve => setTimeout(resolve, 5000));

        // 스크린샷 저장
        const screenshotPath = path.resolve(process.cwd(), 'artifacts', 'blog_manage_screenshot.png');
        await session.page.screenshot({
            path: screenshotPath,
            fullPage: true
        });
        console.log(`📷 스크린샷 저장: ${screenshotPath}`);

        // 임시글 링크 찾기
        try {
            // 임시글 링크 클릭 시도
            const tempLinkSelectors = [
                'a[href*="temp"]',
                'a[href*="Temp"]',
                'a:contains("임시")',
                'a:contains("임시글")',
                '[data-type="temp"]'
            ];

            let tempLinkFound = false;
            for (const selector of tempLinkSelectors) {
                try {
                    await session.page.waitForSelector(selector, { timeout: 2000 });
                    await session.page.click(selector);
                    tempLinkFound = true;
                    console.log(`✅ 임시글 링크 발견: ${selector}`);
                    break;
                } catch (e) {
                    // 다음 선택자 시도
                }
            }

            if (tempLinkFound) {
                await new Promise(resolve => setTimeout(resolve, 3000));

                // 임시글 페이지 스크린샷
                const tempScreenshotPath = path.resolve(process.cwd(), 'artifacts', 'temp_posts_final_screenshot.png');
                await session.page.screenshot({
                    path: tempScreenshotPath,
                    fullPage: true
                });
                console.log(`📷 임시글 페이지 스크린샷: ${tempScreenshotPath}`);

                // 임시글 목록 확인
                const tempPostsInfo = await session.page.evaluate(() => {
                    const info = { posts: [], found: false };

                    // 제목이 "하이디라오"를 포함하는 요소 찾기
                    const titleElements = document.querySelectorAll('*');
                    const postsFound = [];

                    for (let element of titleElements) {
                        const text = element.textContent || '';
                        if (text.includes('하이디라오')) {
                            postsFound.push(text.trim());
                            info.found = true;
                        }
                    }

                    info.posts = [...new Set(postsFound)]; // 중복 제거
                    return info;
                });

                if (tempPostsInfo.found) {
                    console.log('🎉 하이디라오 관련 게시글 발견!');
                    tempPostsInfo.posts.forEach((post, index) => {
                        console.log(`  ${index + 1}. ${post}`);
                    });
                } else {
                    console.log('📝 하이디라오 관련 게시글을 찾을 수 없습니다.');
                }

            } else {
                console.log('⚠️ 임시글 링크를 찾을 수 없습니다.');
            }

        } catch (error) {
            console.log('⚠️ 임시글 검색 중 오류:', error.message);
        }

        console.log('✅ 확인 완료!');
        console.log('⏱️ 20초 후 브라우저를 닫습니다. 수동으로 확인하세요...');
        await new Promise(resolve => setTimeout(resolve, 20000));

        if (session.browser) {
            await session.browser.close();
        }

    } catch (error) {
        console.error('❌ 오류 발생:', error.message);
        process.exit(1);
    }
}

checkBlogManage();
