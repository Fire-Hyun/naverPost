import * as fs from 'fs';
import * as path from 'path';
import * as log from '../utils/logger';

interface GpsCoord {
  latitude: number;
  longitude: number;
}

/**
 * 이미지에서 EXIF GPS 좌표를 추출한다.
 * exifr 라이브러리를 동적 import로 로드.
 */
export async function extractGPS(imagePath: string): Promise<GpsCoord | null> {
  try {
    const exifr = await import('exifr');
    const gps = await exifr.gps(imagePath);
    if (gps && typeof gps.latitude === 'number' && typeof gps.longitude === 'number') {
      return { latitude: gps.latitude, longitude: gps.longitude };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * 카카오 REST API를 이용한 역지오코딩.
 * KAKAO_REST_API_KEY 환경변수가 필요하다.
 */
export async function reverseGeocodeKakao(
  lat: number,
  lng: number,
  apiKey: string
): Promise<string | null> {
  try {
    const url = `https://dapi.kakao.com/v2/local/geo/coord2address.json?x=${lng}&y=${lat}`;
    const res = await fetch(url, {
      headers: { Authorization: `KakaoAK ${apiKey}` },
    });
    if (!res.ok) return null;

    const data: any = await res.json();
    const docs = data.documents;
    if (docs && docs.length > 0) {
      const addr = docs[0].road_address ?? docs[0].address;
      return addr?.address_name ?? null;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * 이미지 디렉토리에서 장소 정보를 추출한다.
 * 1) 첫 번째 GPS 정보가 있는 이미지를 찾음
 * 2) 역지오코딩으로 주소 변환 (API 키가 있으면)
 */
export async function getPlaceFromImages(
  imageDir: string,
  kakaoApiKey?: string
): Promise<{ address: string | null; coords: GpsCoord | null }> {
  if (!fs.existsSync(imageDir)) {
    return { address: null, coords: null };
  }

  const imageFiles = fs.readdirSync(imageDir)
    .filter((f) => /\.(jpe?g|png|gif|webp|bmp)$/i.test(f))
    .map((f) => path.join(imageDir, f));

  for (const imgPath of imageFiles) {
    const gps = await extractGPS(imgPath);
    if (gps) {
      log.info(`GPS 발견: ${path.basename(imgPath)} → ${gps.latitude}, ${gps.longitude}`);

      if (kakaoApiKey) {
        const address = await reverseGeocodeKakao(gps.latitude, gps.longitude, kakaoApiKey);
        if (address) {
          log.info(`역지오코딩 결과: ${address}`);
          return { address, coords: gps };
        }
      }

      return { address: null, coords: gps };
    }
  }

  return { address: null, coords: null };
}
