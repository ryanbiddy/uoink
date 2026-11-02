cask "uoink" do
  version "3.12.1"
  sha256 "5fb2597672c6d8124d153d00d077bb2f1ac053efc5bc9ed2dd8b34fa89cb2a76"

  url "https://github.com/ryanbiddy/uoink/releases/download/v#{version}/Uoink-#{version}-macos-arm64.dmg"
  name "Uoink"
  desc "Save videos, podcasts and articles locally so your AI can search and cite them"
  homepage "https://uoink.app/"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on arch: :arm64
  depends_on macos: :sequoia

  app "Uoink.app"
  binary "#{appdir}/Uoink.app/Contents/Helpers/uoink"

  uninstall launchctl: "com.ryanbiddy.uoink",
            quit:      "com.ryanbiddy.uoink"

  # ~/Library/Application Support/Uoink holds the user's saved library, so
  # zap leaves it in place.
  zap trash: "~/Library/LaunchAgents/com.ryanbiddy.uoink.plist"
end
