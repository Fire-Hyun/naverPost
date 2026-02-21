#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/.runtime"
BUILD_INFO_FILE="${RUNTIME_DIR}/build_info.env"
DEFAULT_SERVICE="naverpost-bot.service"

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

print_warn() {
  echo "[WARN] $*" >&2
}

print_info() {
  echo "[INFO] $*"
}

split_services() {
  local raw="$1"
  raw="${raw//,/ }"
  # shellcheck disable=SC2206
  local arr=( $raw )
  local seen=" "
  local out=()
  local svc
  for svc in "${arr[@]:-}"; do
    [[ -z "${svc}" ]] && continue
    if [[ "${seen}" != *" ${svc} "* ]]; then
      out+=("${svc}")
      seen+="${svc} "
    fi
  done
  printf '%s\n' "${out[@]}"
}

resolve_services() {
  if [[ -n "${SERVICES:-}" ]]; then
    split_services "${SERVICES}"
    return
  fi

  local candidates=()
  while IFS= read -r svc; do
    [[ -z "${svc}" ]] && continue
    # 템플릿/백업 성격 파일명 제외
    if [[ "${svc}" == *"-fixed.service" ]]; then
      continue
    fi
    candidates+=("${svc}")
  done < <(
    cd "${PROJECT_ROOT}" && \
      find . -type f -name '*.service' -print \
      | sed 's#^./##' \
      | xargs -r -n1 basename \
      | sort -u
  )

  if [[ " ${candidates[*]} " != *" ${DEFAULT_SERVICE} "* ]]; then
    candidates+=("${DEFAULT_SERVICE}")
  fi

  if ! has_cmd systemctl; then
    printf '%s\n' "${DEFAULT_SERVICE}"
    return
  fi

  local installed=()
  while IFS= read -r unit; do
    [[ -z "${unit}" ]] && continue
    installed+=("${unit}")
  done < <(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}')

  local matched=()
  local svc
  for svc in "${candidates[@]:-}"; do
    if [[ " ${installed[*]} " == *" ${svc} "* ]]; then
      matched+=("${svc}")
    fi
  done

  if [[ ${#matched[@]} -eq 0 ]]; then
    printf '%s\n' "${DEFAULT_SERVICE}"
    return
  fi

  printf '%s\n' "${matched[@]}"
}

SYSTEMCTL_PREFIX=()
setup_systemctl_prefix() {
  if ! has_cmd systemctl; then
    echo "[ERROR] systemctl not found" >&2
    exit 1
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    SYSTEMCTL_PREFIX=()
    return
  fi

  if ! has_cmd sudo; then
    print_warn "Not root and sudo not found. systemctl may fail."
    SYSTEMCTL_PREFIX=()
    return
  fi

  SYSTEMCTL_PREFIX=(sudo)
  if sudo -n true 2>/dev/null; then
    print_info "sudo non-interactive access is available"
  else
    print_warn "sudo password may be required for systemctl/journalctl commands"
  fi
}

run_systemctl() {
  "${SYSTEMCTL_PREFIX[@]}" systemctl "$@"
}

run_journalctl() {
  "${SYSTEMCTL_PREFIX[@]}" journalctl "$@"
}

main() {
  setup_systemctl_prefix

  mapfile -t SERVICES_LIST < <(resolve_services)
  if [[ ${#SERVICES_LIST[@]} -eq 0 ]]; then
    SERVICES_LIST=("${DEFAULT_SERVICE}")
  fi

  print_info "Service list: ${SERVICES_LIST[*]}"

  print_info "1) Stopping services"
  local svc
  for svc in "${SERVICES_LIST[@]}"; do
    print_info "Stopping ${svc}"
    run_systemctl stop "${svc}"
  done

  print_info "2) Removing dist directory (mandatory)"
  rm -rf "${PROJECT_ROOT}/dist"

  print_info "3) Running npm run build"
  (
    cd "${PROJECT_ROOT}"
    npm run build
  )

  mkdir -p "${RUNTIME_DIR}"
  local build_at git_commit
  build_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  git_commit="$(cd "${PROJECT_ROOT}" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
  {
    echo "BUILD_AT=${build_at}"
    echo "GIT_COMMIT=${git_commit}"
  } > "${BUILD_INFO_FILE}"
  print_info "Build metadata written: ${BUILD_INFO_FILE}"

  print_info "4) Restarting services"
  for svc in "${SERVICES_LIST[@]}"; do
    print_info "Restarting ${svc}"
    run_systemctl restart "${svc}"
  done

  print_info "5) Checking service health"
  local failed=()
  for svc in "${SERVICES_LIST[@]}"; do
    if run_systemctl is-active --quiet "${svc}"; then
      print_info "ACTIVE: ${svc}"
    else
      failed+=("${svc}")
      print_warn "INACTIVE: ${svc}"
    fi
  done

  if [[ ${#failed[@]} -gt 0 ]]; then
    for svc in "${failed[@]}"; do
      echo "----- status: ${svc} -----"
      run_systemctl status --no-pager "${svc}" || true
      echo "----- journal (last 100): ${svc} -----"
      run_journalctl -u "${svc}" -n 100 --no-pager || true
    done
    exit 1
  fi

  exit 0
}

main "$@"
