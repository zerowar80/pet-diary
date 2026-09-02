# 반려견 AI 사진 일기장 (MVP)

사진을 올리면 AI가 상황을 보고 짧은 일기를 대신 써주는 홈서버용 웹서비스입니다.
코드를 직접 수정하지 않아도 아래 순서대로 따라 하면 실행됩니다.

설치 방법은 두 가지입니다.
- **A. Docker Compose** — 일반 서버/NAS에서 가장 간단
- **B. Proxmox LXC (네이티브 설치)** — Docker 중첩 없이 LXC 안에서 바로 실행, 더 가볍습니다

---

## 0. GitHub 비공개 저장소에 올리기

이 폴더는 이미 로컬 git 저장소로 초기화되어 있고(`git init` + 최초 커밋 완료), 아래 순서만 진행하면 됩니다.

**GitHub CLI(`gh`)가 있는 경우 (가장 간단)**
```bash
cd pet-diary
gh repo create pet-diary --private --source=. --remote=origin --push
```

**GitHub 웹사이트에서 직접 만드는 경우**
1. https://github.com/new 에서 저장소 이름을 `pet-diary`로, **Private**로 선택해 생성합니다 (README 등 추가 파일은 체크하지 않습니다).
2. 로컬에서 아래 명령어를 실행합니다.
   ```bash
   cd pet-diary
   git remote add origin git@github.com:내계정/pet-diary.git
   git branch -M main
   git push -u origin main
   ```

> `.env` 파일과 `data/` 폴더(사진, DB)는 `.gitignore`에 포함되어 있어 저장소에 올라가지 않습니다. API 키가 실수로 깃허브에 올라가는 일은 없습니다.

---

## A. Docker Compose로 설치하기

## 1. 준비물

- Docker와 Docker Compose가 설치된 환경 (시놀로지 Container Manager, Proxmox의 Docker VM, 일반 PC/서버 등)
- Anthropic API 키 (https://console.anthropic.com 에서 발급, 유료 사용량 기준 과금)

## 2. 설치 순서

1. 이 폴더 전체를 서버에 업로드합니다.
2. `.env.example` 파일을 복사해서 `.env` 라는 이름으로 저장합니다.
3. `.env` 파일을 열어 아래처럼 본인의 API 키를 붙여넣습니다.

   ```
   ANTHROPIC_API_KEY=sk-ant-실제발급받은키
   ```

4. 터미널(또는 시놀로지 SSH 콘솔)에서 이 폴더로 이동한 뒤 아래 명령어를 실행합니다.

   ```bash
   docker compose up -d --build
   ```

5. 잠시 기다린 뒤, 브라우저에서 아래 주소로 접속합니다.

   ```
   http://서버IP:8000
   ```

   같은 컴퓨터에서 테스트한다면 `http://localhost:8000` 으로 접속하면 됩니다.

## 3. 사용 방법

1. 우측 상단 "사진 올리기" 버튼을 누릅니다.
2. 반려견 이름(예: 우동이)과 사진을 선택하고 업로드합니다.
3. AI가 사진을 분석해 견종을 추정하고 짧은 일기를 자동으로 써줍니다.
4. 같은 이름으로 계속 사진을 올리면 그 아이의 앨범에 시간순으로 쌓입니다.
5. 홈 화면에서 등록된 모든 반려견 앨범을 확인할 수 있습니다.

---

## B. Proxmox LXC로 설치하기 (Docker 없이 네이티브 실행)

LXC 안에서 Docker를 중첩 실행(nesting)하는 대신, Python을 직접 설치해 systemd 서비스로 등록하는 방식입니다. 더 가볍고 재시작 시 자동으로 켜집니다.

### B-1. LXC 컨테이너 새로 만들기 (Proxmox 호스트에서)

이미 만들어둔 LXC가 있다면 이 단계는 건너뛰고 B-2로 이동하세요.

```bash
# Proxmox 호스트 쉘에서
bash scripts/create-lxc-container.sh 210 192.168.0.210/24 192.168.0.1
```
- `210` = 컨테이너 VMID (원하는 번호로 변경 가능)
- `192.168.0.210/24` = 컨테이너에 부여할 고정 IP
- `192.168.0.1` = 공유기/게이트웨이 IP

### B-2. 컨테이너 안에서 앱 설치하기

```bash
pct enter 210
git clone git@github.com:내계정/pet-diary.git   # 0번 단계에서 만든 비공개 저장소
cd pet-diary
cp .env.example .env
nano .env        # ANTHROPIC_API_KEY 값을 실제 키로 수정
bash scripts/install-lxc.sh
```

스크립트가 파이썬 가상환경 생성, 패키지 설치, 전용 실행 계정 생성, systemd 서비스 등록까지 한 번에 처리합니다.

### B-3. 확인 및 관리 명령어

```bash
systemctl status pet-diary      # 실행 상태 확인
journalctl -u pet-diary -f      # 실시간 로그 보기
systemctl restart pet-diary     # 재시작
```

브라우저에서 `http://192.168.0.210:8000` 으로 접속합니다.

### B-4. 코드 업데이트 시

```bash
pct enter 210
cd pet-diary
git pull
systemctl restart pet-diary
```

---

## 4. 데이터는 어디에 저장되나요?

- 사진: `data/uploads/` 폴더 (반려견 이름별 하위 폴더)
- 일기 기록: `data/diary.db` (SQLite 파일)

`data` 폴더 전체가 로컬에 그대로 남기 때문에, 외부 클라우드로 사진이나 영상이 나가지 않습니다. (일기 생성을 위해 사진 자체는 Anthropic API로 전송됩니다.)

## 5. 알려진 제한사항 (MVP 단계)

- 같은 반려견을 얼굴만 보고 자동으로 구분하지는 못합니다. 업로드할 때 이름을 직접 입력해야 합니다.
- 여러 장을 한 번에 올리는 기능은 아직 없고, 한 번에 한 장씩 업로드합니다.
- 아직 인증(로그인) 기능이 없으므로, 외부에 노출하지 않고 홈네트워크 안에서만 사용하는 것을 권장합니다.

## 6. 다음 단계로 고도화하고 싶다면

- 여러 장 동시 업로드 + 월간 하이라이트 자동 생성
- 반려견 얼굴 임베딩 기반 자동 인식 (이름 태깅 없이 구분)
- 짧은 노래 가사 생성 기능 추가
- 로그인/사용자별 격리
