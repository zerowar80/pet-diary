# 반려견 AI 사진 일기장

사진을 올리면 AI가 상황을 보고 짧은 일기를 대신 써주는 홈서버용 웹서비스입니다.
회원가입/로그인이 있어 각자 자신의 반려견 앨범만 관리하며, 반려견은 이름 제한 없이 자유롭게 추가·수정·삭제할 수 있습니다.
일기를 생성할 AI는 업로드할 때마다 Claude / Gemini / ChatGPT 중 골라 쓸 수 있습니다.

설치 방법은 두 가지입니다.
- **A. Docker Compose** — 일반 서버/NAS에서 가장 간단
- **B. Proxmox LXC (네이티브 설치)** — Docker 중첩 없이 LXC 안에서 바로 실행, 더 가볍습니다

---

## 0. GitHub Desktop으로 비공개 저장소에 올리기

이 폴더는 이미 로컬 git 저장소로 초기화되어 있어요(`git init` + 커밋 완료). GitHub Desktop만 있으면 명령어 없이 그대로 올릴 수 있습니다.

1. GitHub Desktop을 엽니다.
2. 왼쪽 위 **File(파일) → Add local repository(로컬 저장소 추가)** 를 클릭합니다.
3. 압축을 푼 `pet-diary` 폴더를 선택하고 **Add repository(저장소 추가)** 를 누릅니다. (이미 git 저장소이므로 바로 인식됩니다.)
4. 화면 위쪽에 **Publish repository(저장소 게시)** 버튼이 보입니다. 클릭합니다.
5. 게시 창에서:
   - Name: `pet-diary` (원하는 이름으로 변경 가능)
   - **Keep this code private(비공개로 유지)** 체크박스를 반드시 체크합니다.
   - **Publish repository** 버튼을 누릅니다.
6. 완료되면 GitHub 웹사이트에 비공개 저장소가 생성됩니다.

이후 코드를 수정했을 때는 GitHub Desktop 왼쪽에 변경된 파일 목록이 보이고, 아래 **Commit(커밋)** 버튼으로 커밋한 뒤 위쪽 **Push origin(푸시)** 버튼만 누르면 됩니다.

> `.env` 파일과 `data/` 폴더(사진, DB)는 `.gitignore`에 포함되어 있어 GitHub Desktop의 변경 목록에도 나타나지 않습니다. API 키가 실수로 올라가는 일은 없습니다.

---

## A. Docker Compose로 설치하기

## 1. 준비물

- Docker와 Docker Compose가 설치된 환경 (시놀로지 Container Manager, Proxmox의 Docker VM, 일반 PC/서버 등)
- 아래 AI 중 최소 한 곳의 API 키
  - Claude: https://console.anthropic.com
  - Gemini: https://aistudio.google.com/app/apikey
  - ChatGPT: https://platform.openai.com/api-keys
  - 모두 사용량 기준 과금이며, 여러 개를 등록해두면 업로드할 때마다 원하는 AI를 골라 쓸 수 있습니다.

## 2. 설치 순서

1. 이 폴더 전체를 서버에 업로드합니다.
2. `.env.example` 파일을 복사해서 `.env` 라는 이름으로 저장합니다.
3. `.env` 파일을 열어 사용할 AI의 API 키를 입력합니다. 쓰지 않는 AI는 빈 칸으로 둬도 됩니다.

   ```
   ANTHROPIC_API_KEY=sk-ant-실제발급받은키
   GOOGLE_API_KEY=실제발급받은키
   OPENAI_API_KEY=실제발급받은키
   SESSION_SECRET=무작위로-긴-문자열로-반드시-변경
   ```

   `SESSION_SECRET`은 로그인 세션을 암호화하는 값으로, 아무 문자열이나 길게(예: 32자 이상) 바꿔서 넣어주세요. `APP_PORT`는 비워두면 8000번을 씁니다. 다른 포트를 쓰고 싶으면 `APP_PORT=9090`처럼 원하는 숫자를 적으세요.

4. 터미널(또는 시놀로지 SSH 콘솔)에서 이 폴더로 이동한 뒤 아래 명령어를 실행합니다.

   ```bash
   docker compose up -d --build
   ```

5. 잠시 기다린 뒤, 브라우저에서 아래 주소로 접속합니다.

   ```
   http://서버IP:<APP_PORT에 적은 포트, 기본 8000>
   ```

   같은 컴퓨터에서 테스트한다면 `http://localhost:8000` 으로 접속하면 됩니다.

## 3. 사용 방법

1. 처음 접속하면 로그인 화면이 뜹니다. **회원가입**으로 계정을 만드세요. 계정마다 반려견 앨범이 서로 분리되어, 다른 사람과 같은 서버를 써도 내 사진은 나만 볼 수 있습니다.
2. 로그인 후 우측 상단 "사진 올리기"를 누릅니다.
3. 반려견 이름(만두·우동이가 아니어도 됩니다. 초코, 보리, 나비 등 이름 제한 없이 자유롭게 입력), 사진, 그리고 일기를 써줄 AI(Claude / Gemini / ChatGPT)를 선택해 업로드합니다.
4. AI가 사진을 분석해 견종을 추정하고 짧은 일기를 자동으로 써줍니다.
5. 같은 이름을 다시 입력하면(입력창에 기존에 등록한 이름이 자동완성으로 떠요) 그 아이의 앨범에 시간순으로 쌓입니다.
6. 홈 화면 각 반려견 카드의 "수정" 버튼으로 이름·견종을 바꾸거나, 앨범 전체를 삭제할 수 있습니다.
7. 각 일기 카드의 "삭제" 버튼으로 사진 한 장 단위로도 지울 수 있습니다.

---

## B. Proxmox LXC로 설치하기 (Docker 없이 네이티브 실행)

LXC 안에서 Docker를 중첩 실행(nesting)하는 대신, Python을 직접 설치해 systemd 서비스로 등록하는 방식입니다. 더 가볍고 재시작 시 자동으로 켜집니다.

설치 방법은 두 가지 중 편한 걸로 고르세요.

### B-0. (추천) 한 번에 배포하기

Proxmox 호스트 쉘에서 아래 한 줄이면 **빈 VMID 자동 탐색 → 저장소 자동 선택 → 컨테이너 생성(IP는 공유기 DHCP로 자동 할당) → git 설치 → 저장소 clone → .env 준비**까지 자동으로 끝납니다. 회원님이 넣는 건 GitHub 저장소 주소(와 선택적으로 PAT)뿐입니다.

```bash
bash scripts/deploy-to-proxmox.sh <GitHub저장소HTTPS주소> [GitHub PAT]

# 예) 저장소가 공개(Public)라면 PAT 없이:
bash scripts/deploy-to-proxmox.sh https://github.com/내계정/pet-diary.git

# 저장소가 비공개(Private)라면 PAT를 추가로:
bash scripts/deploy-to-proxmox.sh https://github.com/내계정/pet-diary.git ghp_여기에토큰
```
- VMID, 컨테이너를 만들 저장소(storage), IP 모두 Proxmox가 자동으로 찾아서 씁니다.
- PAT는 저장소가 비공개일 때만 필요합니다. 공개 저장소라면 두 번째 인자를 생략하면 됩니다.
- 실행 중간에 자동으로 정해진 VMID, 저장소, 할당된 IP가 화면에 출력됩니다.
- DHCP로 받은 IP는 공유기 재시작 등으로 바뀔 수 있어요. 계속 같은 주소를 쓰고 싶으면 공유기 관리화면에서 이 컨테이너의 MAC 주소를 고정 IP로 예약(DHCP reservation)해두는 걸 추천합니다.
- 자동으로 고른 값이 마음에 안 들면 환경변수로 직접 지정할 수 있습니다.
  ```bash
  STORAGE=local-lvm STATIC_IP=192.168.0.210/24 GATEWAY=192.168.0.1 \
  bash scripts/deploy-to-proxmox.sh https://github.com/내계정/pet-diary.git ghp_토큰
  ```
- 자동 처리가 끝나면 아래 단계만 남습니다 (화면에 출력된 VMID로 바꿔서 입력하세요). `install-lxc.sh`를 실행하면 사용할 AI API 키를 그 자리에서 직접 입력받으니 `.env`를 따로 편집할 필요는 없습니다.
  ```bash
  pct enter <출력된VMID>
  bash /root/pet-diary/scripts/install-lxc.sh
  ```

이 스크립트가 편하지 않다면 아래 B-1 / B-2 단계별 방식을 그대로 따라 하셔도 결과는 동일합니다.

> **보안 참고**: 명령어에 PAT를 직접 적으면 쉘 히스토리에 남습니다. 신경 쓰이면 PAT 없이 실행한 뒤(B-2 방식대로) 컨테이너 안에서 직접 clone하세요. 사용한 PAT는 https://github.com/settings/tokens 에서 언제든 삭제(Revoke)할 수 있습니다.

### B-1. LXC 컨테이너만 따로 만들기 (Proxmox 호스트에서)

이미 만들어둔 LXC가 있다면 이 단계는 건너뛰고 B-2로 이동하세요.

```bash
# Proxmox 호스트 쉘에서
bash scripts/create-lxc-container.sh 210
# 고정 IP나 저장소를 직접 쓰려면: STORAGE=local-lvm STATIC_IP=192.168.0.210/24 GATEWAY=192.168.0.1 bash scripts/create-lxc-container.sh 210
```
- `210` = 컨테이너 VMID (원하는 번호로 변경 가능)
- 저장소(storage)는 자동으로 감지된 곳을 사용합니다.

### B-2. 컨테이너 안에서 앱 설치하기

비공개 저장소이므로 clone할 때 GitHub 로그인이 필요합니다. 가장 쉬운 방법은 Personal Access Token(PAT)을 만드는 것입니다.

1. GitHub 웹사이트 → 우측 상단 프로필 → **Settings → Developer settings → Personal access tokens → Tokens (classic)** → **Generate new token**에서 `repo` 권한만 체크해 토큰을 하나 만듭니다.
2. 컨테이너 안에서 clone할 때 비밀번호 대신 이 토큰을 붙여넣습니다.

```bash
pct enter 210
git clone https://github.com/내계정/pet-diary.git
cd pet-diary
# Username: 내계정 / Password: 위에서 만든 토큰 붙여넣기
bash scripts/install-lxc.sh
```

`install-lxc.sh`를 실행하면 사용할 AI의 API 키와 접속 포트(그냥 Enter 시 기본 8000)를 화면에서 바로 입력받습니다. `.env`를 미리 만들거나 편집할 필요는 없습니다 (안 쓰는 AI는 Enter로 건너뛰면 됩니다). SESSION_SECRET(로그인 보안 키)도 자동으로 생성됩니다.

스크립트가 파이썬 가상환경 생성, 패키지 설치, 전용 실행 계정 생성, systemd 서비스 등록까지 한 번에 처리합니다.

### B-3. 확인 및 관리 명령어

```bash
systemctl status pet-diary      # 실행 상태 확인
journalctl -u pet-diary -f      # 실시간 로그 보기
systemctl restart pet-diary     # 재시작
```

브라우저에서 `http://컨테이너IP:설치때입력한포트(기본 8000)` 으로 접속합니다.

### B-4. 코드 업데이트 시

```bash
pct enter 210
cd pet-diary
git pull
systemctl restart pet-diary
```

---

## 4. 계정 및 반려견 관리

- **회원가입/로그인**: 사용자마다 독립된 반려견 목록을 가집니다. 다른 사람이 같은 서버에 가입해도 서로의 사진과 일기를 볼 수 없습니다.
- **비밀번호 변경**: 상단 "계정" 메뉴에서 로그인 상태로 직접 변경할 수 있습니다. (이메일 발송 방식의 비밀번호 찾기는 SMTP 서버가 필요해 아직 지원하지 않습니다.)
- **반려견 추가**: 업로드 화면에서 새 이름을 입력하면 자동으로 새 앨범이 만들어집니다. 만두·우동이처럼 예시로 든 이름이 아니어도 어떤 이름의 강아지든 자유롭게 추가할 수 있습니다.
- **여러 장 한 번에 업로드**: 업로드 화면에서 사진을 여러 장 선택하면, 장마다 각각 AI가 별도의 일기를 생성해 한 번에 앨범에 쌓입니다.
- **반려견 수정**: 홈 화면 카드의 "수정" 버튼 → 이름/견종을 바꾸고 저장.
- **반려견 삭제**: 같은 수정 화면 아래 "이 반려견 앨범 삭제하기" → 해당 반려견의 사진과 일기가 모두 삭제됩니다 (되돌릴 수 없음).
- **일기(사진) 개별 삭제**: 앨범 화면에서 각 일기 카드의 "삭제" 버튼.

## 5. AI 선택은 어떻게 동작하나요?

업로드 화면의 "일기를 써줄 AI" 항목에서 Claude / Gemini / ChatGPT 중 하나를 고를 수 있습니다. `.env`에 키가 입력되지 않은 AI를 선택하면 해당 업로드만 오류 메시지가 저장되니, 사용하려는 AI의 키가 `.env`에 들어있는지 먼저 확인하세요. 각 일기 카드에는 어떤 AI가 작성했는지도 함께 표시됩니다.

## 6. 데이터는 어디에 저장되나요?

- 사진: `data/uploads/<사용자ID>/<반려견이름>/` 폴더
- 계정·일기 기록: `data/diary.db` (SQLite 파일)

`data` 폴더 전체가 로컬에 그대로 남기 때문에, 외부 클라우드로 사진이나 영상이 나가지 않습니다. (일기 생성을 위해 사진 자체는 선택한 AI 제공사의 API로 전송됩니다.)

## 7. 알려진 제한사항 (MVP 단계)

- 같은 반려견을 얼굴만 보고 자동으로 구분하지는 못합니다. 업로드할 때 이름을 직접 입력(또는 자동완성으로 선택)해야 합니다.
- 이메일 발송 기반 비밀번호 찾기, 이메일 인증 기능은 아직 없습니다. 로그인 상태에서만 비밀번호를 바꿀 수 있어, 비밀번호를 완전히 잊으면 관리자가 DB에서 직접 계정을 확인해야 합니다.

## 8. 다음 단계로 고도화하고 싶다면

- 월간 하이라이트 자동 생성
- 반려견 얼굴 임베딩 기반 자동 인식 (이름 태깅 없이 구분)
- 짧은 노래 가사 생성 기능 추가
- SMTP 연동을 통한 이메일 기반 비밀번호 재설정
